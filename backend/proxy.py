"""/v1/chat/completions — the OpenAI-compatible SSE endpoint the Agora engine talks to.

The tool loop runs here and the engine only ever sees final assistant text (PRD 6.3).
Conversation history belongs to the engine (it resends it, bounded by max_history);
what belongs to us is the lead state, so that is the only thing this module keeps.
"""
import json
import os
import time

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from . import playbook, rtm, state
from .tools import REGISTRY, SPECS, calendar, crm, escalation

router = APIRouter()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_KEY = os.getenv("GROQ_API_KEY", "")
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
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
    payload = {"id": rid, "object": "chat.completion.chunk", "model": MODEL,
               "choices": [{"index": 0, "delta": {"content": content} if content else {},
                            "finish_reason": finish}]}
    return f"data: {json.dumps(payload)}\n\n"


# A non-interruptible turn needs a first-chunk metadata packet (PRD 6.3). We use the
# engine's greeting_message for the AI disclosure instead, so nothing needs it yet.


async def respond(sid: str, history: list[dict]) -> str:
    """Run the tool loop against the LLM and return the text to speak."""
    messages = playbook.build(state.get(sid), history)
    for _ in range(MAX_TOOL_HOPS):
        reply = await complete(messages)
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
    """Execute one tool and publish what the dashboard needs to see."""
    try:
        result = _dispatch(sid, name, args)
    except Exception as exc:  # noqa: BLE001 — a bad tool call is the model's problem to handle
        print(f"[proxy] tool {name} failed: {exc!r}")
        result = {"error": type(exc).__name__, "detail": str(exc)}
    rtm.publish(sid, "tool_call", {"name": name, "args": args,
                                   "result_summary": _summarise(name, result)})
    return result


def _dispatch(sid: str, name: str, args: dict) -> dict:
    if name == "update_lead_state":
        lead = state.update(sid, **args)
        rtm.publish(sid, "lead_state", lead)
        crm.sync_contact(lead)  # debounced, fire-and-forget
        return lead

    if name == "book_meeting":
        result = calendar.book_meeting(session_id=sid, **args)
        if "error" not in result:
            lead = state.update(sid, next_action="book_demo", email=args.get("email"))
            rtm.publish(sid, "lead_state", lead)
            crm.create_deal(lead, result)
            rtm.publish(sid, "outcome", {"kind": "meeting_booked", "detail": result})
        return result

    if name == "escalate_to_human":
        lead = state.update(sid, next_action="escalate")
        rtm.publish(sid, "lead_state", lead)
        result = escalation.escalate_to_human(args.get("reason", ""), lead, rtm.channel_for(sid))
        rtm.publish(sid, "escalation", {"reason": args.get("reason", ""),
                                        "summary": result["summary"], "channel": result["channel"]})
        rtm.publish(sid, "outcome", {"kind": "escalated", "detail": {"reason": args.get("reason", "")}})
        return result

    if name in REGISTRY:
        return REGISTRY[name](**args)
    return {"error": "unknown_tool", "name": name}


def _summarise(name: str, result: dict) -> str:
    if name == "get_pricing" and "tier" in result:
        return f"{result['tier']}, ${result['per_seat_month']}/seat"
    if name == "update_lead_state":
        return f"{result.get('seat_count') or '?'} seats, {result.get('qualification')}"
    if "error" in result:
        return f"error: {result['error']}"
    return str(result)[:120]


async def complete(messages: list[dict]) -> dict:
    """One LLM round trip. Returns the assistant message, tool calls included."""
    if not GROQ_KEY:
        # ponytail: no key means text-mode smoke testing, never a silent production fallback
        return {"role": "assistant", "content": "[no GROQ_API_KEY set]"}
    payload = {"model": MODEL, "messages": messages, "stream": False,
               "tools": [{"type": "function", "function": s} for s in SPECS]}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(GROQ_URL, json=payload,
                              headers={"Authorization": f"Bearer {GROQ_KEY}"})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]
