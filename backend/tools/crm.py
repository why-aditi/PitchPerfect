"""HubSpot CRM, credentials per agent. Fire-and-forget after the reply is sent — a CRM
failure must never break a live call, so every error here is logged and swallowed.
"""
import time

import httpx

from ..models import AgentSecrets

API = "https://api.hubapi.com/crm/objects/2026-03"
DEBOUNCE_S = 10

_last_sync: dict[str, float] = {}


def _post(secrets: AgentSecrets, path: str, payload: dict) -> dict | None:
    try:
        r = httpx.post(f"{API}/{path}", timeout=8, json=payload,
                       headers={"Authorization": f"Bearer {secrets.hubspot_token}"})
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        print(f"[crm] {path} failed: {exc!r}")
        return None


def _properties(lead: dict) -> dict:
    status = {"hot": "OPEN_DEAL", "warm": "IN_PROGRESS", "cold": "NEW"}[lead["qualification"]]
    objections = ", ".join(lead["objections_raised"]) or "none"
    competitors = ", ".join(lead["competitor_mentions"]) or "none"
    return {
        "company": lead.get("company") or "",
        "hs_lead_status": status,
        "message": (f"{lead.get('seat_count') or '?'} seats · "
                    f"{lead.get('use_case') or 'unknown use case'} · "
                    f"objections: {objections} · competitors: {competitors}"),
    }


def sync_contact(secrets: AgentSecrets, lead: dict, force: bool = False) -> None:
    """Debounced upsert. No email means no stable identity, so nothing is written yet —
    the state stays in memory until the prospect gives one."""
    sid = lead["session_id"]
    if not force and time.time() - _last_sync.get(sid, 0) < DEBOUNCE_S:
        return
    _last_sync[sid] = time.time()

    email = lead.get("email")
    if not email:
        print(f"[crm] {sid}: no email yet, holding {lead['qualification']} lead in memory")
        return
    if not secrets.hubspot_token:
        print(f"[crm] would upsert {email}: {lead.get('company')} / {lead.get('seat_count')} seats")
        return

    props = {k: v for k, v in _properties(lead).items() if v}
    _post(secrets, "contacts/batch/upsert",
          {"inputs": [{"id": email, "idProperty": "email", "properties": props}]})


def create_deal(secrets: AgentSecrets, lead: dict, booking: dict) -> None:
    who = lead.get("company") or booking.get("email")
    name = f"{who} — {lead.get('seat_count') or '?'} seats"
    if not secrets.hubspot_token:
        print(f"[crm] would create deal: {name} ({booking.get('booking_id')})")
        return
    _post(secrets, "deals", {"properties": {
        "dealname": name,
        "pipeline": secrets.hubspot_pipeline,
        "dealstage": secrets.hubspot_deal_stage,
        "description": (f"Demo booked for {booking.get('slot_iso')} via PitchPilot "
                        f"({lead['session_id']})"),
    }})
