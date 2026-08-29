"""Cal.com. Stub until Phase 3 — the interface is what the proxy depends on (PRD 15)."""
import os
from datetime import datetime, timedelta, timezone

CALCOM_API_KEY = os.getenv("CALCOM_API_KEY")
_booked: dict[str, dict] = {}  # session_id -> booking, keeps book_meeting idempotent


def check_slots(days_ahead: int = 5) -> dict:
    if not CALCOM_API_KEY:
        # ponytail: local stub, swap for the Cal.com availability call in Phase 3
        base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        slots = [base + timedelta(days=d, hours=h) for d in range(1, days_ahead) for h in (10, 15)][:5]
        return {"slots": [{"iso": s.isoformat(), "human": s.strftime("%a %d %b, %H:%M UTC")} for s in slots]}
    raise NotImplementedError("Cal.com availability")


def book_meeting(slot_iso: str, email: str, name: str | None = None, session_id: str = "") -> dict:
    if not email:
        return {"error": "email_required", "instruction": "Ask for their email before booking."}
    if session_id in _booked:
        return {"already_booked": True, **_booked[session_id]}
    booking = {"slot_iso": slot_iso, "email": email, "name": name, "booking_id": f"stub_{len(_booked) + 1}"}
    _booked[session_id] = booking
    return booking
