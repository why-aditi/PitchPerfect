"""/v1/chat/completions — OpenAI-compatible SSE the Agora engine talks to (PRD 6.3).

The tool loop runs here; the engine only ever sees final assistant text.
"""
import json
import os
import time

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from . import playbook, rtm, state
from .tools import REGISTRY, SPECS

router = APIRouter()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_KEY = os.getenv("GROQ_API_KEY", "")
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
PROXY_SECRET = os.getenv("LLM_PROXY_SECRET", "")
MAX_TOOL_HOPS = 4

_history: dict[str, list[dict]] = {}


@router.post("/v1/chat/completions")
async def completions(request: Request, session_id: str = "", authorization: str = Header("")):
    if PROXY_SECRET and PROXY_SECRET not in authorization:
        raise HTTPException(401, "bad proxy secret")
    body = await request.json()
    # The engine adds turn_id and timestamp to each message because vendor is "custom"; ignore them.
    incoming = [{"role": m["role"], "content": m.get("content") or ""} for m in body.get("messages", [])
                if m["role"] != "system"]
    sid = session_id or "text-test"
    history = _history.setdefault(sid, [])
    history[:] = incoming or history
    return StreamingResponse(_stream(sid, history), media_type="text/event-stream")


async def _stream(sid: str, history: list[dict]):
    text = await _respond(sid, history)
    history.append({"role": "assistant", "content": text})
    rid = f"resp-{int(time.time() * 1000)}"
    for word in text.split(" "):
        yield _chunk(rid, word + " ")
    yield _chunk(rid, "", finish="stop")
    yield "data: [DONE]\n\n"


def _chunk(rid: str, content: str, finish=None) -> str:
    payload = {"id": rid, "object": "chat.completion.chunk", "model": MODEL,
               "choices": [{"index": 0, "delta": {"content": content} if content else {},
                            "finish_reason": finish}]}
    return f"data: {json.dumps(payload)}\n\n"


def metadata_chunk(rid: str, interruptable: bool = False) -> str:
    """First chunk only — the engine reads metadata from chunk 1 and ignores its choices."""
    payload = {"id": rid, "object": "chat.completion.custom_metadata",
               "choices": [], "metadata": {"interruptable": interruptable}}
    return f"data: {json.dumps(payload)}\n\n"


async def _respond(sid: str, history: list[dict]) -> str:
    """Run the tool loop, return the final spoken text."""
    messages = playbook.build(state.get(sid), history)
    for _ in range(MAX_TOOL_HOPS):
        reply = await _complete(messages)
        calls = reply.get("tool_calls")
        if not calls:
            return reply.get("content") or "Sorry, could you say that again?"
        messages.append(reply)
        for call in calls:
            messages.append({"role": "tool", "tool_call_id": call["id"],
                             "content": json.dumps(_run_tool(sid, call))})
    return "Let me get a colleague to help with that."


def _run_tool(sid: str, call: dict) -> dict:
    name = call["function"]["name"]
    args = json.loads(call["function"].get("arguments") or "{}")
    if name == "update_lead_state":
        result = state.update(sid, **args)
        rtm.publish(sid, "lead_state", result)
    elif name in REGISTRY:
        fn = REGISTRY[name]
        if name in ("book_meeting", "escalate_to_human"):
            args["state" if name == "escalate_to_human" else "session_id"] = (
                state.get(sid) if name == "escalate_to_human" else sid)
        result = fn(**args)
    else:
        result = {"error": "unknown_tool", "name": name}
    rtm.publish(sid, "tool_call", {"name": name, "args": args, "result_summary": str(result)[:120]})
    return result


async def _complete(messages: list[dict]) -> dict:
    if not GROQ_KEY:
        # ponytail: no key means text-mode smoke test, not a silent fallback in production
        return {"role": "assistant", "content": "[no GROQ_API_KEY set]"}
    payload = {"model": MODEL, "messages": messages, "stream": False,
               "tools": [{"type": "function", "function": s} for s in SPECS]}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(GROQ_URL, json=payload, headers={"Authorization": f"Bearer {GROQ_KEY}"})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]
