"""Event publisher for the dashboard: lead_state, tool_call, outcome, escalation,
call_ended. The message envelope is the frozen contract in PRD 6.2.

Transport is SSE, not Agora RTM. The engine delivers transcripts to the client over
its own data channel and the client renders those directly; these events are ours
alone, so they do not need to ride the same channel. Everything funnels through
publish(), so switching to the RTM REST API later touches this function and nothing else.
"""
import asyncio
import time
from typing import Any

_subscribers: list = []          # in-process listeners (tests)
_queues: list[asyncio.Queue] = []  # connected SSE clients


CHANNEL_PREFIX = "pitchpilot-"


def channel_for(session_id: str) -> str:
    """sess_8f2a -> pitchpilot-8f2a. Both are minted from the same suffix in main.py,
    so nothing has to carry the mapping around."""
    return f"{CHANNEL_PREFIX}{session_id.removeprefix('sess_')}"


def events_channel(session_id: str) -> str:
    return f"{channel_for(session_id)}-events"


def publish(session_id: str, type_: str, data: dict[str, Any]) -> dict:
    msg = {"type": type_, "session_id": session_id, "ts": int(time.time() * 1000), "data": data}
    for sub in _subscribers:
        sub(msg)
    for q in list(_queues):
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            _queues.remove(q)  # a dashboard that stopped reading must not stall the call
    return msg


def subscribe(fn) -> None:
    _subscribers.append(fn)


def open_stream() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _queues.append(q)
    return q


def close_stream(q: asyncio.Queue) -> None:
    if q in _queues:
        _queues.remove(q)
