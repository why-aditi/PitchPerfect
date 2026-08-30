"""Prices come from the agent's own knowledge, never from the model's memory."""
from ..models import AgentConfig, Tier


def _serves(tier: Tier, seats: int) -> bool:
    return seats >= tier.min_seats and (tier.max_seats is None or seats <= tier.max_seats)


def _tier_for_seats(tiers: list[Tier], seats: int) -> Tier:
    for tier in tiers:
        if _serves(tier, seats):
            return tier
    # Above every configured band. Falling back the other way would quote the most
    # expensive tier to someone who asked for fewer seats than the cheapest one covers.
    return max(tiers, key=lambda t: t.min_seats)


def get_pricing(config: AgentConfig, tier: str | None = None, seats: int | None = None) -> dict:
    tiers = config.knowledge.tiers
    if not tiers:
        return {"error": "no_data",
                "instruction": "This agent has no pricing configured. Say you'll follow up."}

    # Seat counts arrive from speech transcription, so treat them as untrusted. Quoting a
    # tier for a nonsense number is worse than admitting the number made no sense.
    if seats is not None and seats < 1:
        return {"error": "invalid_seats", "seats": seats,
                "instruction": "That seat count did not make sense. Ask how many seats they need."}

    corrected_from = None
    if tier:
        match = next((t for t in tiers if t.name.lower() == tier.lower()), None)
        if not match:
            return {"error": "no_data", "known_tiers": [t.name for t in tiers]}
        # A named tier that cannot serve this seat count would produce a real quote at a
        # price the prospect can never actually buy. The seat count wins, and the swap is
        # reported so the agent can say why (PRD G3: every price traces to a tool call).
        if seats is not None and not _serves(match, seats):
            corrected_from, match = match.name, _tier_for_seats(tiers, seats)
    else:
        match = _tier_for_seats(tiers, seats or 1)

    per_seat = match.per_seat_month
    if seats and match.volume_break and seats >= match.volume_break["seats"]:
        per_seat = match.volume_break["per_seat_month"]

    out = {"tier": match.name, "per_seat_month": per_seat, "currency": config.knowledge.currency,
           "features": match.features, "volume_break": match.volume_break}
    if corrected_from:
        out["note"] = (f"{corrected_from} does not cover {seats} seats; "
                       f"{match.name} is the tier that applies.")
    if seats:
        out["seats"] = seats
        out["monthly_total"] = per_seat * seats
    return out
