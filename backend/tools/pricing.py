import json
from pathlib import Path

_DATA = json.loads((Path(__file__).parent.parent / "data" / "pricing.json").read_text())


def _tier_for_seats(seats: int) -> dict:
    for tier in _DATA["tiers"]:
        if seats >= tier["min_seats"] and (tier["max_seats"] is None or seats <= tier["max_seats"]):
            return tier
    return _DATA["tiers"][-1]


def get_pricing(tier: str | None = None, seats: int | None = None) -> dict:
    if tier:
        match = next((t for t in _DATA["tiers"] if t["name"].lower() == tier.lower()), None)
        if not match:
            return {"error": "no_data", "known_tiers": [t["name"] for t in _DATA["tiers"]]}
    else:
        match = _tier_for_seats(seats or 1)

    per_seat = match["per_seat_month"]
    if seats and match["volume_break"] and seats >= match["volume_break"]["seats"]:
        per_seat = match["volume_break"]["per_seat_month"]

    out = {"tier": match["name"], "per_seat_month": per_seat, "currency": _DATA["currency"],
           "features": match["features"], "volume_break": match["volume_break"]}
    if seats:
        out["seats"] = seats
        out["monthly_total"] = per_seat * seats
    return out
