"""Event publisher: lead_state, tool_call, outcome, escalation, call_ended (PRD 6.2)."""
import time
from typing import Any

_subscribers: list = []  # ponytail: in-process fan-out; real RTM publish lands in Phase 1


def publish(session_id: str, type_: str, data: dict[str, Any]) -> dict:
    msg = {"type": type_, "session_id": session_id, "ts": int(time.time() * 1000), "data": data}
    for sub in _subscribers:
        sub(msg)
    print(f"[rtm] {msg}")
    return msg


def subscribe(fn) -> None:
    _subscribers.append(fn)


def events_channel(channel: str) -> str:
    return f"{channel}-events"
