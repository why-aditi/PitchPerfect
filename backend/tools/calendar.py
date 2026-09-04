"""Cal.com v2, credentials per agent. With no key configured the tool offers generated
times, so a missing integration degrades to a logged outcome rather than a broken call.

The two endpoints take DIFFERENT cal-api-version headers. Sending the wrong one silently
gets you an older endpoint shape rather than an error.
"""
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from ..models import AgentSecrets

log = logging.getLogger("pitchpilot.calendar")

API = "https://api.cal.com/v2"
SLOTS_VERSION = "2024-09-04"
BOOKINGS_VERSION = "2026-02-25"

_booked: dict[str, dict] = {}  # session_id -> booking; one live booking per call
SETTLE_S = 45   # a re-book inside this is the same intent, not a change of mind
# How far check_slots reaches when the window it was asked about turns out to be empty.
# A working week: far enough that a quiet Friday afternoon still finds something, close
# enough that the agent is not offering a demo three weeks out to someone ready now.
WIDEN_DAYS = 7

# What a prospect actually says on a call. The model relays it verbatim, so the aliases
# have to live on this side of the tool boundary rather than in the schema.
_TZ_ALIASES = {
    "est": "America/New_York", "edt": "America/New_York", "et": "America/New_York",
    "eastern": "America/New_York", "cst": "America/Chicago", "ct": "America/Chicago",
    "central": "America/Chicago", "mst": "America/Denver", "mountain": "America/Denver",
    "pst": "America/Los_Angeles", "pdt": "America/Los_Angeles", "pt": "America/Los_Angeles",
    "pacific": "America/Los_Angeles", "gmt": "UTC", "bst": "Europe/London",
    "uk": "Europe/London", "london": "Europe/London", "cet": "Europe/Berlin",
    "ist": "Asia/Kolkata", "india": "Asia/Kolkata", "sgt": "Asia/Singapore",
    "jst": "Asia/Tokyo", "aest": "Australia/Sydney", "sydney": "Australia/Sydney",
}


def resolve_tz(name: str | None) -> ZoneInfo:
    """Never raise. An unknown zone costs a wrong-looking time; an exception costs the call."""
    if not name:
        return ZoneInfo("UTC")
    key = name.strip().lower()
    try:
        return ZoneInfo(_TZ_ALIASES.get(key, name.strip()))
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _headers(secrets: AgentSecrets, version: str) -> dict:
    return {"Authorization": f"Bearer {secrets.calcom_api_key}", "cal-api-version": version}


def _human(iso: str, tz: ZoneInfo) -> str:
    """The slot as a person would say it out loud: "Tuesday at 11:30pm".

    A display string gets read back verbatim — a live turn produced "Tuesday 01 Sep at
    23:30 EDT" because that is what the tool handed over, and no prompt rule survives
    contact with a tool whose output is already formatted the wrong way. The date and the
    zone are dropped on purpose: the iso rides alongside for the model, and the zone is
    already the prospect's own, so naming it adds nothing a caller would say.
    """
    when = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(tz)
    hour = when.strftime("%I").lstrip("0")
    minute = f":{when.minute:02d}" if when.minute else ""
    return f"{when.strftime('%A')} at {hour}{minute}{when.strftime('%p').lower()}"


# Dictated over a phone line, an email arrives as words. Rejecting that as "no email" is
# the difference between a booked demo and a follow-up promise.
_SPOKEN = [(" at ", "@"), (" dot ", "."), (" underscore ", "_"), (" dash ", "-"),
           (" hyphen ", "-"), (" plus ", "+")]
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$")
# Punctuation ASR sprinkles through a dictated address. Never legal in an unquoted one,
# so removing it can only ever recover an address, never invent one.
_NOISE = str.maketrans("", "", " ,;:!?")


def normalise_email(raw: str) -> str:
    """'aditi dot kala at gmail dot com' -> 'aditi.kala@gmail.com'. Idempotent on real ones."""
    email = " ".join(raw.split()).lower()
    if "@" not in email:
        for word, symbol in _SPOKEN:
            email = email.replace(word, symbol)
    # ASR punctuates speech, and a comma lands inside the address: "EHS Raka, at
    # gmail.com" became "ehsraka,@gmail.com", which _EMAIL accepts (a comma is neither @
    # nor whitespace) and HubSpot rejects with a 400.
    return email.translate(_NOISE)


def clean_email(raw: str) -> str | None:
    """The address, or None if what came back from ASR is not one.

    A live call recorded the prospect's email as "gmail.com" and carried it into the lead
    state and on towards the CRM. Half an address is worse than none: it looks captured,
    so nothing asks again.
    """
    email = normalise_email(raw or "")
    return email if _EMAIL.match(email) else None


def spoken_haystack(text: str) -> str:
    """Free speech flattened the way an address is, so one can be searched for inside it."""
    out = " ".join((text or "").split()).lower()
    for word, symbol in _SPOKEN:
        out = out.replace(word, symbol)
    return out.replace(" ", "")


def was_actually_said(email: str, history: list[dict]) -> bool:
    """Whether the prospect really gave this address.

    Asked to book, a model will supply a plausible one whether or not it heard it: a test
    call in which no email was ever spoken still produced a real Cal.com booking, and Cal
    emailed the invented address. Well-formed is not the same as given, so the check is
    against what was actually said rather than against the shape of the string.
    """
    said = " ".join(m.get("content") or "" for m in history if m.get("role") == "user")
    return _comparable(email) in _comparable(spoken_haystack(said))


def _comparable(text: str) -> str:
    """Both sides of the guard flattened identically, or it refuses real addresses.

    A live call was refused a booking three times: ASR heard "keshavsharma1441. @gmail.com."
    and the model offered the cleaned address, so the stray dot sat in the haystack and not
    in the needle. Dots go too — "dana dot reyes at gmail dot com" still matches
    dana.reyes@gmail.com either way, and an address nobody said still has nothing to match
    against, which is the only thing this guard is for.
    """
    return text.lower().translate(_NOISE).replace(".", "")


def _api_error(exc: httpx.HTTPStatusError) -> dict:
    """Turn a Cal.com failure into something the agent can actually do next.

    A raw HTTPStatusError reaches the model as a status line and a URL, which it cannot
    recover from — a live call hit a 409, the model had no idea the slot had simply gone,
    and the conversation stopped dead. Every branch here ends in an instruction.
    """
    status = exc.response.status_code
    if status == 409:
        return {"error": "slot_taken",
                "instruction": "That time is no longer free. Call check_slots again and "
                               "offer a different one. Do not apologise at length."}
    if status in (401, 403):
        return {"error": "calendar_unavailable",
                "instruction": "Booking is down. Say you will email the invite instead, and "
                               "call update_lead_state with next_action send_followup."}
    detail = _detail(exc.response)
    if status == 400 and "email" in detail:
        # A live call lost a booking to email_domain_cannot_receive_mail and the prospect
        # was told only that it could not be locked in — so nobody learned the address was
        # the problem, and the same address was tried twice more.
        return {"error": "email_rejected", "detail": detail,
                "instruction": "That address was refused as one that cannot receive mail. "
                               "Tell them so, read back what you heard, and ask for another "
                               "address to send the invite to."}
    return {"error": "booking_failed", "status": status, "detail": detail,
            "instruction": "Say you could not lock that in, and offer to email the invite."}


def _detail(response) -> str:
    """Cal.com's own words about what it refused, which are the only actionable part."""
    try:
        body = response.json()
    except ValueError:
        return (response.text or "")[:200]
    inner = body.get("error")
    message = body.get("message") or (inner.get("message") if isinstance(inner, dict) else inner)
    return str(message or "")[:200]


def check_slots(secrets: AgentSecrets, days_ahead: int = 5, timezone_name: str = "UTC") -> dict:
    tz = resolve_tz(timezone_name)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    if not secrets.calcom_api_key or not secrets.calcom_event_type_id:
        # ponytail: fixed 10:00/15:00 local offers. Real availability arrives with the key.
        local = now.astimezone(tz)
        slots = [local.replace(hour=h) + timedelta(days=d)
                 for d in range(1, days_ahead + 1) for h in (10, 15)]
        return {"slots": [{"iso": s.isoformat(), "human": _human(s.isoformat(), tz)}
                          for s in slots[:5]],
                "timezone": str(tz), "source": "stub"}

    picked = _fetch(secrets, now, days_ahead, tz)
    # days_ahead=0 means "today", and it makes start == end, so Cal.com has nothing to
    # return however open the calendar is. The model's answer to an empty list is to ask
    # again with a wider window — a whole extra LLM round trip, and the commonest slow turn
    # in the logs (sess_ff5b turn 5 spent four hops that way). One more HTTP call is ~200ms
    # against ~700ms for the hop it saves, so widen here and let the agent say so.
    widened = False
    if not picked and days_ahead < WIDEN_DAYS:
        picked = _fetch(secrets, now, WIDEN_DAYS, tz)
        widened = bool(picked)

    out = {"slots": [{"iso": iso, "human": _human(iso, tz)} for iso in picked],
           "timezone": str(tz), "source": "cal.com"}
    if widened:
        out["widened"] = True
        out["instruction"] = ("Nothing is free in the window they asked about. Say so in "
                              "half a sentence, then offer these instead — do not call "
                              "check_slots again.")
    return out


_prefetched: dict[str, list[dict]] = {}   # session_id -> the slots the prompt is carrying


def prefetch(secrets: AgentSecrets, session_id: str, timezone_name: str = "UTC") -> None:
    """Warm the session's slots so the prompt can carry them and the agent need not ask.

    A tool turn costs two LLM round trips at minimum — one to emit the call, one to turn
    the result into speech — so "what times are free" was never going to come back inside
    a second while the answer lived behind a tool. Fetched once at /start-call and put in
    the volatile block instead, it is one hop, which is.

    Blocking httpx, so call it in a thread. Failure is silent by design: the tool is still
    there, and a prompt without a slots line is exactly today's behaviour.
    """
    started = time.time()
    try:
        fresh = check_slots(secrets, days_ahead=WIDEN_DAYS, timezone_name=timezone_name)
        slots = fresh.get("slots") or []
        _prefetched[session_id] = slots
        # Logged on success too. Silence here is indistinguishable from a task that never
        # ran, and the question the logs have to answer is whether the agent called
        # check_slots because the prompt was empty or because it ignored a full one.
        log.info("[slots] %s prefetched %d in %dms (%s)", session_id, len(slots),
                 int((time.time() - started) * 1000), fresh.get("source"))
    except Exception as exc:  # noqa: BLE001 — a warm cache is an optimisation, never a gate
        log.warning("[slots] %s prefetch failed: %r", session_id, exc)


def prefetched(session_id: str) -> list[dict]:
    return _prefetched.get(session_id) or []


def drop_prefetched(session_id: str) -> None:
    """After a booking the list has a hole in it, and at hangup it is landfill. Both want
    the prompt to stop quoting times that are no longer true."""
    _prefetched.pop(session_id, None)


def _fetch(secrets: AgentSecrets, now: datetime, days_ahead: int, tz: ZoneInfo) -> list[str]:
    """The slots Cal.com has in this window, as a spoken shortlist.

    Response is {status, data: {"2026-09-01": [{"start": "..."} | "..."]}}, each day's slots
    in order. Taken flat, the first five are five consecutive half hours of one morning,
    which is one option read out five times. Two per day makes it a real choice.
    """
    r = httpx.get(f"{API}/slots", headers=_headers(secrets, SLOTS_VERSION), timeout=8, params={
        "eventTypeId": secrets.calcom_event_type_id,
        "start": now.isoformat(),
        "end": (now + timedelta(days=days_ahead)).isoformat(),
        "timeZone": str(tz),
    })
    r.raise_for_status()
    per_day = [[slot["start"] if isinstance(slot, dict) else slot for slot in day]
               for day in r.json().get("data", {}).values()]
    picked = [iso for day in per_day for iso in day[:2]][:5]
    if len(picked) < 3 and per_day:
        picked = per_day[0][:5]   # only one day is open at all; offer what there is
    return picked


def book_meeting(secrets: AgentSecrets, slot_iso: str, email: str, name: str | None = None,
                 timezone_name: str = "UTC", session_id: str = "") -> dict:
    heard = normalise_email(email or "")
    if not heard:
        return {"error": "email_required", "instruction": "Ask for their email before booking."}
    email = clean_email(heard)
    if email is None:
        # Heard, but not as an address. Reading it back is the only way to fix it on a call.
        return {"error": "email_unclear", "heard": heard,
                "instruction": f"You heard '{heard}'. Read it back and ask them to confirm "
                               f"or spell it."}

    # Cal.com will happily take the local part of the address as the attendee name, which
    # puts "aditi.kala" on the invite and in the CRM. Asking is one short question.
    person = " ".join((name or "").split())
    if len(person) < 2 or person.lower() in (email, email.split("@")[0]):
        return {"error": "name_required",
                "instruction": "Ask who the invite should be for, then book with their name "
                               "and email together. Do not derive a name from the address."}

    tz = resolve_tz(timezone_name)
    existing = _booked.get(session_id)
    if existing:
        if existing["slot_iso"] == slot_iso:
            return {"already_booked": True, **existing}
        # A different slot seconds after the first is the model confirming itself, not the
        # prospect changing their mind: a live call booked and then rescheduled 17 seconds
        # apart, and the prospect got a confirmation email and a "moved" email for one demo.
        # Agreeing a time, hearing it read back and asking to move it cannot happen that
        # fast. ponytail: a wall-clock window, because the turn number is not threaded down
        # here — pass the turn if this ever needs to be exact.
        if time.time() - existing["booked_at"] < SETTLE_S:
            return {"already_booked": True, "ignored_slot": slot_iso, **existing}
        # They really did move it. Booking again would leave two meetings on the calendar.
        return _reschedule(secrets, existing, slot_iso, tz, session_id)

    if not secrets.calcom_api_key or not secrets.calcom_event_type_id:
        booking = {"slot_iso": slot_iso, "email": email, "name": person,
                   "booking_id": f"stub_{len(_booked) + 1}", "source": "stub"}
    else:
        r = httpx.post(f"{API}/bookings", headers=_headers(secrets, BOOKINGS_VERSION), timeout=10,
                       json={
                           "eventTypeId": int(secrets.calcom_event_type_id),
                           "start": slot_iso,
                           "attendee": {"name": person, "email": email,
                                        "timeZone": str(tz), "language": "en"},
                       })
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            return _api_error(exc)
        data = r.json().get("data", {})
        booking = {"slot_iso": data.get("start", slot_iso), "email": email, "name": person,
                   "booking_id": data.get("uid") or data.get("id"), "source": "cal.com"}

    booking["human"] = _human(booking["slot_iso"], tz)
    booking["booked_at"] = time.time()
    _booked[session_id] = booking
    return booking


def cancel_meeting(secrets: AgentSecrets, reason: str = "", session_id: str = "") -> dict:
    """Cancel the meeting THIS call booked. There is no way to name any other one.

    The booking uid is never a parameter — it is read from _booked[session_id], which only
    ever holds what this session created. That is the whole access-control story, and it is
    deliberately structural rather than a check the model could be talked past: a uid
    argument would let a caller cancel a stranger's meeting by guessing or overhearing one,
    and an email argument would let them cancel anything that address had ever booked.

    The cost is that a prospect ringing back to cancel yesterday's demo cannot be served
    here. That is the right trade: identity on this call is an unauthenticated voice, so
    the honest answer is a human, not a lookup.
    """
    booking = _booked.get(session_id)
    if not booking:
        return {"error": "nothing_booked",
                "instruction": "No meeting was booked on this call, so there is nothing to "
                               "cancel. If they mean an earlier booking, say a colleague "
                               "will sort it out and call escalate_to_human."}

    if booking["source"] == "cal.com":
        r = httpx.post(f"{API}/bookings/{booking['booking_id']}/cancel",
                       headers=_headers(secrets, BOOKINGS_VERSION), timeout=10,
                       json={"cancellationReason": reason or "cancelled on the call"})
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            return _api_error(exc)      # the booking stands; do not forget it

    _booked.pop(session_id, None)       # so a later book_meeting starts clean
    return {"cancelled": True, "slot_iso": booking["slot_iso"], "human": booking.get("human"),
            "booking_id": booking["booking_id"], "reason": reason}


def _reschedule(secrets: AgentSecrets, existing: dict, slot_iso: str, tz: ZoneInfo,
                session_id: str) -> dict:
    """v2 links the old and new bookings itself, so this is one call and a new uid back.

    Same cal-api-version as /bookings (2026-02-25) — without it the request silently
    resolves to an older endpoint shape rather than failing.
    """
    moved = {**existing, "slot_iso": slot_iso, "rescheduled_from": existing["slot_iso"]}
    if existing["source"] == "cal.com":
        r = httpx.post(f"{API}/bookings/{existing['booking_id']}/reschedule",
                       headers=_headers(secrets, BOOKINGS_VERSION), timeout=10,
                       json={"start": slot_iso, "reschedulingReason": "moved on the call"})
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            return _api_error(exc)   # the original booking still stands
        data = r.json().get("data", {})
        moved["slot_iso"] = data.get("start", slot_iso)
        moved["booking_id"] = data.get("uid") or data.get("id") or existing["booking_id"]
    moved["human"] = _human(moved["slot_iso"], tz)
    moved["booked_at"] = time.time()
    _booked[session_id] = moved
    return moved
