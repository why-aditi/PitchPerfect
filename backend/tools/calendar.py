"""Cal.com v2. Falls back to generated slots when no key is set, so a missing
integration degrades to a logged outcome instead of a broken call (PRD 15).

The two endpoints take DIFFERENT cal-api-version headers. Sending the wrong one
silently gets you an older endpoint shape rather than an error.
"""
import os
from datetime import datetime, timedelta, timezone

import httpx

API = "https://api.cal.com/v2"
SLOTS_VERSION = "2024-09-04"
BOOKINGS_VERSION = "2026-02-25"

CALCOM_API_KEY = os.getenv("CALCOM_API_KEY", "")
EVENT_TYPE_ID = os.getenv("CALCOM_EVENT_TYPE_ID", "")

_booked: dict[str, dict] = {}  # session_id -> booking; keeps book_meeting idempotent


def _headers(version: str) -> dict:
    return {"Authorization": f"Bearer {CALCOM_API_KEY}", "cal-api-version": version}


def _human(iso: str) -> str:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%a %d %b, %H:%M UTC")


def check_slots(days_ahead: int = 5) -> dict:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    if not CALCOM_API_KEY or not EVENT_TYPE_ID:
        # ponytail: fixed 10:00/15:00 UTC offers. Real availability arrives with the key.
        slots = [now + timedelta(days=d, hours=h) for d in range(1, days_ahead + 1) for h in (10, 15)]
        return {"slots": [{"iso": s.isoformat(), "human": _human(s.isoformat())} for s in slots[:5]],
                "source": "stub"}

    r = httpx.get(f"{API}/slots", headers=_headers(SLOTS_VERSION), timeout=8, params={
        "eventTypeId": EVENT_TYPE_ID,
        "start": now.isoformat(),
        "end": (now + timedelta(days=days_ahead)).isoformat(),
        "timeZone": "UTC",
    })
    r.raise_for_status()
    # Response is {status, data: {"2026-09-01": [{"start": "..."} | "..."]}}
    out = []
    for day in r.json().get("data", {}).values():
        for slot in day:
            iso = slot["start"] if isinstance(slot, dict) else slot
            out.append({"iso": iso, "human": _human(iso)})
    return {"slots": out[:5], "source": "cal.com"}


def book_meeting(slot_iso: str, email: str, name: str | None = None, session_id: str = "") -> dict:
    if not email:
        return {"error": "email_required", "instruction": "Ask for their email before booking."}
    if session_id in _booked:
        return {"already_booked": True, **_booked[session_id]}

    if not CALCOM_API_KEY or not EVENT_TYPE_ID:
        booking = {"slot_iso": slot_iso, "email": email, "name": name,
                   "booking_id": f"stub_{len(_booked) + 1}", "source": "stub"}
    else:
        r = httpx.post(f"{API}/bookings", headers=_headers(BOOKINGS_VERSION), timeout=10, json={
            "eventTypeId": int(EVENT_TYPE_ID),
            "start": slot_iso,
            "attendee": {"name": name or email.split("@")[0], "email": email,
                         "timeZone": "UTC", "language": "en"},
        })
        r.raise_for_status()
        data = r.json().get("data", {})
        booking = {"slot_iso": data.get("start", slot_iso), "email": email, "name": name,
                   "booking_id": data.get("uid") or data.get("id"), "source": "cal.com"}

    _booked[session_id] = booking
    return booking
