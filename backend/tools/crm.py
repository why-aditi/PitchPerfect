"""HubSpot. Fire-and-forget after the reply is sent; a failure must never break a call."""
import os
import time

HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN")
_last_sync: dict[str, float] = {}
DEBOUNCE_S = 10


def sync_contact(state: dict, force: bool = False) -> None:
    sid = state["session_id"]
    if not force and time.time() - _last_sync.get(sid, 0) < DEBOUNCE_S:
        return
    _last_sync[sid] = time.time()
    if not HUBSPOT_TOKEN:
        print(f"[crm] would upsert {sid}: {state['company']} / {state['seat_count']} seats / {state['qualification']}")
        return
    raise NotImplementedError("HubSpot contact upsert")


def create_deal(state: dict, booking: dict) -> None:
    if not HUBSPOT_TOKEN:
        print(f"[crm] would create deal for {state['session_id']}: {booking}")
        return
    raise NotImplementedError("HubSpot deal create")
