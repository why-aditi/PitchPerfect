"""Event publisher for the console: lead_state, tool_call, outcome, escalation,
call_ended. The message envelope is the frozen contract in PRD 6.2.

Transport is SSE, not Agora RTM. The engine delivers transcripts to the client over its
own data channel and the client renders those directly; these events are ours alone, so
they do not need to ride the same channel. Everything funnels through publish(), so
switching to the RTM REST API later touches this function and nothing else.
"""
import asyncio
import time
from typing import Any

_subscribers: list = []                       # in-process listeners (tests)
_queues: list[asyncio.Queue] = []             # connected SSE clients


def channel_for(session_id: str) -> str:
    """sess_8f2a -> pitchpilot-8f2a. Both are minted from the same suffix in main.py,
    so nothing has to carry the mapping around."""
    return f"pitchpilot-{session_id.removeprefix('sess_')}"


def events_channel(session_id: str) -> str:
    return f"{channel_for(session_id)}-events"


def publish(session_id: str, type_: str, data: dict[str, Any]) -> dict:
    from . import agents  # local import: agents never imports rtm, so there is no cycle

    msg = {"type": type_, "session_id": session_id, "ts": int(time.time() * 1000), "data": data}

    # Resolve the owning agent NOW and queue it beside the message. Resolving when the
    # dashboard dequeues would be too late: a call releases its binding as it ends, and
    # call_ended would be dropped as belonging to no agent.
    bound = agents.for_session(session_id)
    agent_id = bound[0] if bound else None

    for sub in _subscribers:
        sub(msg)
    for q in list(_queues):
        try:
            q.put_nowait((agent_id, msg))
        except asyncio.QueueFull:
            _queues.remove(q)  # a dashboard that stopped reading must not stall the call
    return msg


def subscribe(fn) -> None:
    _subscribers.append(fn)


def open_stream() -> asyncio.Queue:
    """Yields (agent_id, message) pairs. agent_id is routing only — it is not part of the
    PRD 6.2 envelope and is never sent to the client."""
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _queues.append(q)
    return q


def close_stream(q: asyncio.Queue) -> None:
    if q in _queues:
        _queues.remove(q)
