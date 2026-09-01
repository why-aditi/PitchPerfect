"""/v1/chat/completions — the OpenAI-compatible SSE endpoint the Agora engine talks to.

The tool loop runs here and the engine only ever sees final assistant text (PRD 6.3).
Conversation history belongs to the engine (it resends it, bounded by max_history);
what belongs to us is the lead state and the agent's config.
"""
import asyncio
import json
import os
import re
import time

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from . import agents, playbook, rtm, state, tools
from .models import AgentConfig, AgentSecrets

router = APIRouter()

# Any OpenAI-compatible chat-completions endpoint. Groq stays the default because that is
# what the agent records name in llm_model, but the provider is the one thing most likely to
# change under this proxy — Groq's free tier is 8000 tokens/minute and a tool-using turn
# costs about 3600, which is roughly four turns of a real call. Swapping providers should
# be two lines of .env, not an edit here.
LLM_URL = os.getenv("LLM_URL") or "https://api.groq.com/openai/v1/chat/completions"
LLM_KEY = os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY", "")
PROXY_SECRET = os.getenv("LLM_PROXY_SECRET", "")
MAX_TOOL_HOPS = 4


@router.post("/v1/chat/completions")
async def completions(request: Request, session_id: str = "", authorization: str = Header("")):
    if PROXY_SECRET and PROXY_SECRET not in authorization:
        raise HTTPException(401, "bad proxy secret")
    body = await request.json()
    # vendor="custom" adds turn_id and timestamp to every message; we only need role/content.
    history = [{"role": m["role"], "content": m.get("content") or ""}
               for m in body.get("messages", []) if m.get("role") != "system"]
    return StreamingResponse(_stream(session_id or "text-test", history),
                             media_type="text/event-stream")


async def _stream(sid: str, history: list[dict]):
    """Stream the final text. Never raise — a dead SSE stream is a dead call."""
    try:
        text = await respond(sid, history)
    except Exception as exc:  # noqa: BLE001 — the engine's failure_message covers the spoken side
        # The history is logged with the error because the engine's exact message shape is
        # the one thing we cannot see from here, and a failing turn is indistinguishable
        # from a working one to the prospect: both just hear the fallback line.
        shape = [(m.get("role"), len(m.get("content") or "")) for m in history]
        print(f"[proxy] {sid} failed: {exc}\n[proxy] incoming history: {shape}")
        state.update(sid, next_action="send_followup",
                     notes=[f"call degraded: {type(exc).__name__}"])
        text = "Sorry — give me one moment."

    rid = f"resp-{int(time.time() * 1000)}"
    for word in text.split(" "):
        yield _chunk(rid, word + " ")
    yield _chunk(rid, "", finish="stop")
    yield "data: [DONE]\n\n"


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


async def respond(sid: str, history: list[dict]) -> str:
    """Run the tool loop against the LLM and return the text to speak."""
    config, secrets = _bound(sid)
    messages = playbook.build(config, state.get(sid), history)
    specs = tools.specs_for(config)

    for _ in range(MAX_TOOL_HOPS):
        reply = await complete(config, messages, specs)
        calls = reply.get("tool_calls")
        if not calls:
            return reply.get("content") or "Sorry, could you say that again?"
        messages.append(reply)
        for call in calls:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            messages.append({"role": "tool", "tool_call_id": call["id"], "name": name,
                             "content": json.dumps(run_tool(sid, name, args, history))})
    return "Let me bring in a colleague who can help with that."


def run_tool(sid: str, name: str, args: dict, history: list[dict] | None = None) -> dict:
    """Execute one tool and publish what the console needs to see."""
    try:
        result = _dispatch(sid, name, args, history or [])
    except Exception as exc:  # noqa: BLE001 — a bad tool call is the model's problem to recover from
        print(f"[proxy] tool {name} failed: {exc!r}")
        result = {"error": type(exc).__name__, "detail": str(exc)}
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
        tools.sync_contact(secrets, lead)  # debounced, fire-and-forget
        return lead

    if name == "get_pricing":
        return tools.get_pricing(config, **args)

    if name == "get_battlecard":
        return tools.get_battlecard(config, **args)

    if name == "check_slots":
        return tools.check_slots(secrets, **args)

    if name == "book_meeting":
        result = tools.book_meeting(secrets, session_id=sid, **args)
        # One demo is one outcome and one deal, however many times it is agreed or moved.
        # already_booked is the idempotent repeat; rescheduled_from is the prospect moving
        # it mid-call. Both leave the existing booking standing, so re-announcing either
        # would put a second meeting on the console and a duplicate deal in the CRM.
        settled = result.get("already_booked") or "rescheduled_from" in result
        if "error" not in result and not settled:
            lead = state.update(sid, next_action="book_demo", email=result.get("email"))
            rtm.publish(sid, "lead_state", lead)
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
    """
    from . import agents, agora

    engine_agent_id = agents.engine_agent(sid)
    if not engine_agent_id:
        return  # text-mode session, or a call that never reached the engine

    async def speak():
        try:
            await agora.speak(engine_agent_id, text, interrupt=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[proxy] hand-off line not spoken: {exc!r}")

    try:
        asyncio.get_running_loop().create_task(speak())
    except RuntimeError:
        pass  # no loop (a sync test); the escalation event still went out


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


async def complete(config: AgentConfig, messages: list[dict], specs: list[dict],
                   resamples: int = 1) -> dict:
    """One LLM round trip. Returns the assistant message, tool calls included."""
    if not LLM_KEY:
        # ponytail: no key means text-mode smoke testing, never a silent production fallback
        return {"role": "assistant", "content": "[no LLM_API_KEY / GROQ_API_KEY set]"}
    payload = {"model": config.llm_model, "messages": messages, "stream": False,
               "tools": [{"type": "function", "function": s} for s in specs]}
    async with httpx.AsyncClient(timeout=20) as client:
        for attempt in range(resamples + 1):
            r = await client.post(LLM_URL, json=payload,
                                  headers={"Authorization": f"Bearer {LLM_KEY}"})
            if not r.is_error:
                return r.json()["choices"][0]["message"]
            if attempt < resamples and _should_resample(r.status_code, r.text):
                # ponytail: one extra round trip, no backoff. A live call cannot wait, and
                # the alternative is the prospect hearing the fallback line for this turn.
                print(f"[proxy] resampling after tool_use_failed: {r.text[:200]}")
                continue
            wait = _retry_after(r.status_code, r.headers, r.text)
            if attempt < resamples and wait is not None:
                print(f"[proxy] rate limited, waiting {wait}s then retrying")
                await asyncio.sleep(wait)
                continue
            # Groq names the offending field in the body. Without it a 400 here is
            # indistinguishable from any other failure, and every turn just becomes the
            # fallback line — which is what "it says it has to look that up" sounds like.
            raise RuntimeError(f"LLM {r.status_code} from {LLM_URL}: {r.text[:400]}")
