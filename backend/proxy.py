"""/v1/chat/completions — the OpenAI-compatible SSE endpoint the Agora engine talks to.

The tool loop runs here and the engine only ever sees final assistant text (PRD 6.3).
Conversation history belongs to the engine (it resends it, bounded by max_history);
what belongs to us is the lead state and the agent's config.

Latency shape of a turn, and why the code is arranged the way it is:

- The engine starts TTS on the first complete sentence it receives, so text is forwarded
  the moment the LLM produces it (stream_turn). Buffering the reply and chunking it word
  by word afterwards — the original design — put the whole generation in front of the
  first audio on every turn.
- Lead capture is not on this path at all. It runs beside the reply in extract.py, so a
  turn that needs no tool is one LLM round trip, not two.
- The upstream client is shared. A fresh TLS handshake per hop measured ~0.5s on Mistral.
- Tools that call out (Cal.com, HubSpot, Slack) use a blocking client and run in a worker
  thread, so a slow booking stalls only its own call.
"""
import asyncio
import json
import logging
import os
import re
import time

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from . import agents, extract, playbook, rtm, state, tools
from .models import AgentConfig, AgentSecrets

log = logging.getLogger("pitchpilot.proxy")
router = APIRouter()

# Any OpenAI-compatible chat-completions endpoint. Groq stays the default because that is
# what the agent records name in llm_model, but the provider is the one thing most likely to
# change under this proxy. Swapping providers should be two lines of .env, not an edit here.
LLM_URL = os.getenv("LLM_URL") or "https://api.groq.com/openai/v1/chat/completions"
LLM_KEY = os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY", "")
PROXY_SECRET = os.getenv("LLM_PROXY_SECRET", "")
MAX_TOOL_HOPS = 4
# A live turn cannot wait long. connect is generous for a cold provider; read is per
# chunk once the stream is open, so a stalled provider is a dead turn in ten seconds
# rather than twenty.
LLM_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)

# What the engine speaks when a turn dies here. Not "one moment": a line that asks the
# prospect to go again is honest about what happened and does not leave them waiting for
# an answer that is not coming.
FALLBACK = "Sorry, I lost you for a second there. Could you say that again?"


@router.post("/v1/chat/completions")
async def completions(request: Request, session_id: str = "", authorization: str = Header("")):
    if PROXY_SECRET and PROXY_SECRET not in authorization:
        raise HTTPException(401, "bad proxy secret")
    sid = session_id or "text-test"
    if agents.for_session(sid) is None:
        # A session this process never started. The wrong backend answering this with a
        # 200 and an apology is exactly what hid a tunnel pointed at another machine for
        # a whole call, so it is an error the engine gets to see as one.
        log.error("%s turn for a session this process has not bound — is PUBLIC_BASE_URL "
                  "forwarding to this backend?", sid)
        raise HTTPException(404, f"no agent bound to session {sid}")
    body = await request.json()
    # vendor="custom" adds turn_id and timestamp to every message; we only need role/content.
    history = [{"role": m["role"], "content": m.get("content") or ""}
               for m in body.get("messages", []) if m.get("role") != "system"]
    turn_id = body.get("turn_id")
    return StreamingResponse(_stream(sid, history, turn_id),
                             media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def _stream(sid: str, history: list[dict], turn_id=None):
    """SSE for the engine. Never raise — a dead SSE stream is a dead call."""
    rid = f"resp-{int(time.time() * 1000)}"
    started = time.perf_counter()
    first = None
    spoken = []
    try:
        async for piece in stream_turn(sid, history):
            if first is None:
                first = time.perf_counter()
            spoken.append(piece)
            yield _chunk(rid, piece)
    except Exception as exc:  # noqa: BLE001 — the engine's failure_message covers the spoken side
        # The history is logged with the error because the engine's exact message shape is
        # the one thing we cannot see from here, and a failing turn is indistinguishable
        # from a working one to the prospect: both just hear the fallback line.
        shape = [(m.get("role"), len(m.get("content") or "")) for m in history]
        log.error("%s turn failed: %r\n[proxy] incoming history: %s", sid, exc, shape)
        state.update(sid, next_action="send_followup",
                     notes=[f"call degraded: {type(exc).__name__}"])
        for word in FALLBACK.split(" "):
            yield _chunk(rid, word + " ")
    yield _chunk(rid, "", finish="stop")
    yield "data: [DONE]\n\n"
    now = time.perf_counter()
    log.info("[turn] %s turn=%s ttft=%dms total=%dms said=%r", sid, turn_id,
             int(((first or now) - started) * 1000), int((now - started) * 1000),
             "".join(spoken)[:120])


def _chunk(rid: str, content: str, finish: str | None = None) -> str:
    payload = {"id": rid, "object": "chat.completion.chunk",
               "choices": [{"index": 0, "delta": {"content": content} if content else {},
                            "finish_reason": finish}]}
    return f"data: {json.dumps(payload)}\n\n"


# A non-interruptible turn needs a first-chunk metadata packet (PRD 6.3). We use the
# engine's greeting_message for the AI disclosure instead, so nothing needs it yet.


def _bound(sid: str) -> tuple[AgentConfig, AgentSecrets]:
    """The agent pinned to this call at /start-call (PRD 11)."""
    bound = agents.for_session(sid)
    if bound is None:
        raise HTTPException(404, f"no agent bound to session {sid}")
    _, config, secrets = bound
    return config, secrets


async def stream_turn(sid: str, history: list[dict]):
    """Yield the reply's text as the LLM produces it.

    respond() runs as a task and pushes pieces through a queue; this generator drains it.
    A complete() that never streams (the scripted fakes, a tool-only cut-off) still ends
    with the final text being yielded once, so the engine always hears something.
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    streamed = False

    async def sink(piece: str) -> None:
        nonlocal streamed
        if piece:
            streamed = True
            await queue.put(piece)

    async def produce() -> None:
        try:
            text = await respond(sid, history, sink=sink)
            if not streamed and text:
                await queue.put(text)
        finally:
            await queue.put(None)

    task = asyncio.create_task(produce())
    try:
        while True:
            piece = await queue.get()
            if piece is None:
                break
            yield piece
        await task      # surfaces a failure to _stream, which speaks the fallback line
    finally:
        if not task.done():
            task.cancel()


async def respond(sid: str, history: list[dict], sink=None) -> str:
    """Run the tool loop against the LLM and return the text to speak.

    sink, if given, receives text pieces as they stream from the final hop. The return
    value is the whole text either way, so text-mode callers need not care.
    """
    config, secrets = _bound(sid)
    messages = playbook.build(config, state.get(sid), history)
    specs = tools.specs_for(config)
    hops = []
    try:
        for _ in range(MAX_TOOL_HOPS):
            t0 = time.perf_counter()
            reply = await complete(config, messages, specs, sink=sink)
            calls = reply.get("tool_calls")
            hops.append((int((time.perf_counter() - t0) * 1000),
                         [c["function"]["name"] for c in calls] if calls else "text"))
            if not calls:
                text = reply.get("content") or ""
                if text.strip():
                    return text
                # Nothing to say: the fallback line goes through the sink too, so a
                # streaming caller hears it.
                text = "Sorry, could you say that again?"
                if sink is not None:
                    await sink(text)
                return text
            messages.append(reply)
            for call in calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = await asyncio.to_thread(run_tool, sid, name, args, history)
                messages.append({"role": "tool", "tool_call_id": call["id"], "name": name,
                                 "content": json.dumps(result)})
        text = "Let me bring in a colleague who can help with that."
        if sink is not None:
            await sink(text)
        return text
    finally:
        log.info("[hops] %s %s", sid, hops)
        # Lead capture runs beside the next turn, never in front of this one.
        extract.schedule(sid, history)


def run_tool(sid: str, name: str, args: dict, history: list[dict] | None = None) -> dict:
    """Execute one tool and publish what the console needs to see.

    Called from a worker thread by the turn loop; rtm.publish is thread-safe for that.
    """
    try:
        result = _dispatch(sid, name, args, history or [])
    except Exception as exc:  # noqa: BLE001 — a bad tool call is the model's problem to recover from
        log.warning("tool %s failed: %r", name, exc)
        result = {"error": type(exc).__name__, "detail": str(exc)}
    # Also to the log, not only to RTM: RTM is live-only, so once a call ends the one
    # record of what the model actually did is gone, and "it said it would book but
    # nothing was booked" becomes unanswerable after the fact.
    log.info("[tool] %s %s(%s) -> %s", sid, name, json.dumps(args, default=str)[:300],
             _summarise(name, result))
    rtm.publish(sid, "tool_call", {"name": name, "args": args,
                                   "result_summary": _summarise(name, result)})
    return result


def _dispatch(sid: str, name: str, args: dict, history: list[dict]) -> dict:
    config, secrets = _bound(sid)

    # A disabled tool is absent from the specs, so the model should never ask for one.
    # If it does anyway, refusing here keeps the switch meaningful.
    if name not in tools.enabled_names(config) and name != "update_lead_state":
        return {"error": "tool_disabled", "name": name}

    if name == "update_lead_state":
        # Same trust boundary as booking: ASR turns a dictated address into words, and a
        # live call stored "gmail.com" as the email and carried it towards the CRM.
        if "email" in args:
            args = {**args, "email": tools.clean_email(args["email"] or "")}
        lead = state.update(sid, **args)
        rtm.publish(sid, "lead_state", lead)
        # update_lead_state is exempt from the tool gate above (the agent must always be
        # able to remember), but the CRM write hanging off it is not — the switch is the
        # only thing standing between a test call and someone's live pipeline.
        if config.tools_enabled.crm:
            tools.sync_contact(secrets, lead)  # debounced, fire-and-forget
        return lead

    if name == "get_pricing":
        return tools.get_pricing(config, **args)

    if name == "get_battlecard":
        return tools.get_battlecard(config, **args)

    if name == "check_slots":
        return tools.check_slots(secrets, **args)

    if name == "book_meeting":
        # The address is checked against what was actually said, not just against the shape
        # of the string: a live call invented adam@example.com for a prospect who had given
        # her own, and only Cal.com refusing the domain stopped a stranger being emailed.
        heard = tools.clean_email(args.get("email") or "")
        if heard and not tools.was_actually_said(heard, history):
            return {"error": "email_not_heard",
                    "instruction": "You have not heard that address on this call. Ask for "
                                   "their email and book with exactly what they say."}
        result = tools.book_meeting(secrets, session_id=sid, **args)
        # One demo is one outcome and one deal, however many times it is agreed or moved.
        # already_booked is the idempotent repeat; rescheduled_from is the prospect moving
        # it mid-call. Both leave the existing booking standing, so re-announcing either
        # would put a second meeting on the console and a duplicate deal in the CRM.
        settled = result.get("already_booked") or "rescheduled_from" in result
        if "error" not in result and not settled:
            lead = state.update(sid, next_action="book_demo", email=result.get("email"))
            rtm.publish(sid, "lead_state", lead)
            if config.tools_enabled.crm:
                tools.create_deal(secrets, lead, result)
            rtm.publish(sid, "outcome", {"kind": "meeting_booked", "detail": result})
        return result

    if name == "cancel_meeting":
        result = tools.cancel_meeting(secrets, session_id=sid, **args)
        if result.get("cancelled"):
            # The demo is off, so the call's next step is a follow-up rather than a booking.
            # No outcome is published: the meeting_booked chip already went out and the
            # console shows the cancel as its own tool call.
            lead = state.update(sid, next_action="send_followup",
                                notes=[f"cancelled the demo: {args.get('reason') or 'no reason given'}"])
            rtm.publish(sid, "lead_state", lead)
        return result

    if name == "escalate_to_human":
        reason = args.get("reason", "")
        lead = state.update(sid, next_action="escalate")
        rtm.publish(sid, "lead_state", lead)
        result = tools.escalate_to_human(secrets, reason, lead, rtm.channel_for(sid))
        rtm.publish(sid, "escalation", {"reason": reason, "summary": result["summary"],
                                        "channel": result["channel"]})
        rtm.publish(sid, "outcome", {"kind": "escalated", "detail": {"reason": reason}})
        _say_aloud(sid, result["rep_eta"])
        return result

    return {"error": "unknown_tool", "name": name}


def _money(value: float) -> str:
    """39.0 reads as 39; 19.5 stays 19.5. Config stores prices as numbers, not strings."""
    return str(int(value)) if float(value).is_integer() else str(value)


def _say_aloud(sid: str, text: str) -> None:
    """Speak a line through the engine rather than through the reply (PRD 19 q3).

    The hand-off line has to be heard. Returning it as text puts it at the mercy of the
    turn: the model may reword it, bury it, or be mid-sentence when the rep arrives.
    Fire-and-forget, because a hand-off that also blocks the reply is worse than one that
    is not announced, and never fatal — the escalation itself has already been published.
    Works from the tool worker thread too: rtm remembers the app's loop.
    """
    from . import agents, agora

    engine_agent_id = agents.engine_agent(sid)
    if not engine_agent_id:
        return  # text-mode session, or a call that never reached the engine

    async def speak():
        try:
            await agora.speak(engine_agent_id, text, interrupt=True)
        except Exception as exc:  # noqa: BLE001
            log.warning("hand-off line not spoken: %r", exc)

    loop = rtm.app_loop()
    if loop is None:
        return  # no loop (a sync test); the escalation event still went out
    try:
        if asyncio.get_running_loop() is loop:
            loop.create_task(speak())
            return
    except RuntimeError:
        pass
    asyncio.run_coroutine_threadsafe(speak(), loop)


def _summarise(name: str, result: dict) -> str:
    if name == "get_pricing" and "tier" in result:
        return f"{result['tier']}, ${_money(result['per_seat_month'])}/seat"
    if name == "update_lead_state":
        return f"{result.get('seat_count') or '?'} seats, {result.get('qualification')}"
    if "error" in result:
        return f"error: {result['error']}"
    return str(result)[:120]


# A live call cannot wait long, but Groq's free tier names a wait that is usually shorter
# than the filler phrase already playing. Anything past this and the prospect is sitting in
# silence, so the turn is better spent on the fallback line.
# Measured against the real thing: a live turn was refused a retry because Groq asked for
# 4.0875s and the cap was 4.0. Free-tier waits land just under five, and five seconds of a
# filler phrase beats a dead turn and a prospect saying "hello?".
MAX_WAIT_S = 5.0


def _retry_after(status_code: int, headers, body: str) -> float | None:
    """Seconds to wait before trying a rate-limited request again, or None to give up.

    A 429 on free-tier TPM is the commonest way a real call dies: the system prompt, the
    tool specs and the history are resent every request, so a few tool-using turns clear
    8000 tokens/minute. Groq names the wait, and it is typically 2-4 seconds — long, but a
    slow answer beats a dead turn, and the filler phrase is already covering the gap.
    """
    if status_code != 429:
        return None
    wait = headers.get("retry-after")
    if wait is None:
        match = re.search(r"try again in ([0-9.]+)s", body)
        wait = match.group(1) if match else None
    try:
        seconds = float(wait)
    except (TypeError, ValueError):
        return None
    return seconds if 0 < seconds <= MAX_WAIT_S else None


def _should_resample(status_code: int, body: str) -> bool:
    """Whether a Groq failure is a bad sample rather than a bad request.

    gpt-oss leaks its own channel token into the function name it emits — a live turn
    produced `update_lead_state<|channel|>analysis` — and Groq rejects the call against
    request.tools before we ever see it, so we cannot sanitise it on our side. It is a
    sampling artifact, not a schema problem, so drawing again usually clears it. Groq
    labels exactly this class `tool_use_failed`.
    """
    return status_code == 400 and "tool_use_failed" in body


# --- the upstream round trip ---------------------------------------------------------------

_client: httpx.AsyncClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


def _http() -> httpx.AsyncClient:
    """One keep-alive client per event loop. A connection is reused across hops and
    turns; a fresh handshake per request measured ~0.5s against Mistral."""
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client_loop is not loop:
        _client = httpx.AsyncClient(timeout=LLM_TIMEOUT,
                                    limits=httpx.Limits(max_keepalive_connections=8,
                                                        keepalive_expiry=60))
        _client_loop = loop
    return _client


async def complete(config: AgentConfig, messages: list[dict], specs: list[dict],
                   resamples: int = 1, sink=None, model: str | None = None,
                   tool_choice=None) -> dict:
    """One LLM round trip. Returns the assistant message, tool calls included.

    Streams: text deltas go to sink as they arrive, tool-call deltas are accumulated into
    the returned message. The engine hears the first sentence while the rest is still
    being generated, which is the single largest latency lever a custom LLM has.
    """
    if not LLM_KEY:
        # ponytail: no key means text-mode smoke testing, never a silent production fallback
        return {"role": "assistant", "content": "[no LLM_API_KEY / GROQ_API_KEY set]"}
    payload = {"model": model or config.llm_model, "messages": messages, "stream": True,
               "tools": [{"type": "function", "function": s} for s in specs]}
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice
    headers = {"Authorization": f"Bearer {LLM_KEY}", "Accept": "text/event-stream"}
    client = _http()
    for attempt in range(resamples + 1):
        async with client.stream("POST", LLM_URL, json=payload, headers=headers) as r:
            if not r.is_error:
                message = {"role": "assistant", "content": ""}
                async for kind, value in _parse_sse(r.aiter_lines()):
                    if kind == "text" and sink is not None:
                        await sink(value)
                    elif kind == "message":
                        message = value
                return message
            body = (await r.aread()).decode(errors="replace")
            status = r.status_code
        if attempt < resamples and _should_resample(status, body):
            # ponytail: one extra round trip, no backoff. A live call cannot wait, and
            # the alternative is the prospect hearing the fallback line for this turn.
            log.warning("resampling after tool_use_failed: %s", body[:200])
            continue
        wait = _retry_after(status, r.headers, body)
        if attempt < resamples and wait is not None:
            log.warning("rate limited, waiting %ss then retrying", wait)
            await asyncio.sleep(wait)
            continue
        # The provider names the offending field in the body. Without it a 400 here is
        # indistinguishable from any other failure, and every turn just becomes the
        # fallback line — which is what "it says it has to look that up" sounds like.
        raise RuntimeError(f"LLM {status} from {LLM_URL}: {body[:400]}")
    raise RuntimeError(f"LLM gave up after {resamples + 1} attempts")


async def _parse_sse(lines):
    """Turn an OpenAI-style chat.completion.chunk stream into ("text", piece) events and
    one final ("message", assistant_message). Tolerant of keepalives, blank lines, junk,
    and a stream that ends without [DONE]."""
    content: list[str] = []
    calls: dict[int, dict] = {}
    async for line in lines:
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        piece = delta.get("content")
        if piece:
            content.append(piece)
            yield "text", piece
        for tc in delta.get("tool_calls") or []:
            index = tc.get("index", len(calls))
            slot = calls.setdefault(index, {"id": None, "type": "function",
                                            "function": {"name": "", "arguments": ""}})
            if tc.get("id"):
                slot["id"] = tc["id"]
            fn = tc.get("function") or {}
            if fn.get("name"):
                slot["function"]["name"] = fn["name"]
            if fn.get("arguments"):
                slot["function"]["arguments"] += fn["arguments"]
    message = {"role": "assistant", "content": "".join(content)}
    if calls:
        ordered = [calls[i] for i in sorted(calls)]
        for n, call in enumerate(ordered):
            call["id"] = call["id"] or f"call_{n}"
        message["tool_calls"] = ordered
        if not message["content"]:
            message["content"] = None
    yield "message", message
