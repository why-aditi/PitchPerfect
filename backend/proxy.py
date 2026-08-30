"""/v1/chat/completions — the OpenAI-compatible SSE endpoint the Agora engine talks to.

The tool loop runs here and the engine only ever sees final assistant text (PRD 6.3).
Conversation history belongs to the engine (it resends it, bounded by max_history);
what belongs to us is the lead state and the agent's config.
"""
import asyncio
import json
import os
import time

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from . import agents, playbook, rtm, state, tools
from .models import AgentConfig, AgentSecrets

router = APIRouter()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_KEY = os.getenv("GROQ_API_KEY", "")
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
        print(f"[proxy] {sid} failed: {exc!r}")
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
                             "content": json.dumps(run_tool(sid, name, args))})
    return "Let me bring in a colleague who can help with that."


def run_tool(sid: str, name: str, args: dict) -> dict:
    """Execute one tool and publish what the console needs to see."""
    try:
        result = _dispatch(sid, name, args)
    except Exception as exc:  # noqa: BLE001 — a bad tool call is the model's problem to recover from
        print(f"[proxy] tool {name} failed: {exc!r}")
        result = {"error": type(exc).__name__, "detail": str(exc)}
    rtm.publish(sid, "tool_call", {"name": name, "args": args,
                                   "result_summary": _summarise(name, result)})
    return result


def _dispatch(sid: str, name: str, args: dict) -> dict:
    config, secrets = _bound(sid)

    # A disabled tool is absent from the specs, so the model should never ask for one.
    # If it does anyway, refusing here keeps the switch meaningful.
    if name not in tools.enabled_names(config) and name != "update_lead_state":
        return {"error": "tool_disabled", "name": name}

    if name == "update_lead_state":
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
        # already_booked is the idempotent path: the booking stands, but re-announcing it
        # would put a second meeting_booked on the console for one demo.
        if "error" not in result and not result.get("already_booked"):
            lead = state.update(sid, next_action="book_demo", email=args.get("email"))
            rtm.publish(sid, "lead_state", lead)
            tools.create_deal(secrets, lead, result)
            rtm.publish(sid, "outcome", {"kind": "meeting_booked", "detail": result})
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


async def complete(config: AgentConfig, messages: list[dict], specs: list[dict]) -> dict:
    """One LLM round trip. Returns the assistant message, tool calls included."""
    if not GROQ_KEY:
        # ponytail: no key means text-mode smoke testing, never a silent production fallback
        return {"role": "assistant", "content": "[no GROQ_API_KEY set]"}
    payload = {"model": config.llm_model, "messages": messages, "stream": False,
               "tools": [{"type": "function", "function": s} for s in specs]}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(GROQ_URL, json=payload,
                              headers={"Authorization": f"Bearer {GROQ_KEY}"})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]
