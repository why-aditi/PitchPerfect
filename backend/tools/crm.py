"""HubSpot CRM. Fire-and-forget after the reply is sent — a CRM failure must never
break a live call, so every error here is logged and swallowed (PRD 15).
"""
import os
import time

import httpx

API = "https://api.hubapi.com/crm/objects/2026-03"
HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN", "")
DEAL_PIPELINE = os.getenv("HUBSPOT_PIPELINE", "default")
DEAL_STAGE = os.getenv("HUBSPOT_DEAL_STAGE", "appointmentscheduled")
DEBOUNCE_S = 10

_last_sync: dict[str, float] = {}


def _post(path: str, payload: dict) -> dict | None:
    try:
        r = httpx.post(f"{API}/{path}", timeout=8, json=payload,
                       headers={"Authorization": f"Bearer {HUBSPOT_TOKEN}"})
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        print(f"[crm] {path} failed: {exc!r}")
        return None


def _properties(lead: dict) -> dict:
    return {
        "company": lead.get("company") or "",
        "hs_lead_status": {"hot": "OPEN_DEAL", "warm": "IN_PROGRESS", "cold": "NEW"}[lead["qualification"]],
        "message": (f"{lead.get('seat_count') or '?'} seats · {lead.get('use_case') or 'unknown use case'} · "
                    f"objections: {', '.join(lead['objections_raised']) or 'none'} · "
                    f"competitors: {', '.join(lead['competitor_mentions']) or 'none'}"),
    }


def sync_contact(lead: dict, force: bool = False) -> None:
    """Debounced upsert. No email means no stable identity, so nothing is written yet —
    the state is still in memory and gets flushed once the prospect gives one."""
    sid = lead["session_id"]
    if not force and time.time() - _last_sync.get(sid, 0) < DEBOUNCE_S:
        return
    _last_sync[sid] = time.time()

    email = lead.get("email")
    if not email:
        print(f"[crm] {sid}: no email yet, holding {lead['qualification']} lead in memory")
        return
    if not HUBSPOT_TOKEN:
        print(f"[crm] would upsert {email}: {lead.get('company')} / {lead.get('seat_count')} seats")
        return

    props = {k: v for k, v in _properties(lead).items() if v}
    _post("contacts/batch/upsert",
          {"inputs": [{"id": email, "idProperty": "email", "properties": props}]})


def create_deal(lead: dict, booking: dict) -> None:
    name = f"{lead.get('company') or booking.get('email')} — {lead.get('seat_count') or '?'} seats"
    if not HUBSPOT_TOKEN:
        print(f"[crm] would create deal: {name} ({booking.get('booking_id')})")
        return
    _post("deals", {"properties": {
        "dealname": name,
        "pipeline": DEAL_PIPELINE,
        "dealstage": DEAL_STAGE,
        "description": f"Demo booked for {booking.get('slot_iso')} via PitchPilot ({lead['session_id']})",
    }})
