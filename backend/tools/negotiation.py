"""Concessions come from the agent's own ladder, never from the model's memory.

The same rule pricing.py is built on, applied to the other half of a sales conversation.
A price the model invents is a wrong number said confidently; a concession the model
invents is a commitment the company did not make, and the second one is worse, because a
wrong price gets corrected on the next turn and a promised free pilot gets honoured.

The agent already had this hole. Its pricing strategy told it to "offer a pilot" and
nothing in the config said what a pilot was — how long, how many seats, at what price —
so every pilot it ever offered was improvised. This module is where a pilot now lives.

One rung at a time, in the operator's order, each with the thing that has to come back
before it is given. When the ladder runs out the answer is a human, not a better price.
"""
from ..models import AgentConfig, Concession

# Read out as written, like get_pricing's. The model is not asked to phrase the trade:
# the half a model reliably drops under pressure is the half after the comma.
def _spoken(rung: Concession) -> str:
    return f"What I can do is {rung.give} — if {rung.require}."


def _eligible(rung: Concession, seats: int | None) -> bool:
    """An unknown seat count does not disqualify anything. Refusing to concede because
    nobody has said a number yet would make the agent stubborn at exactly the wrong
    moment; the operator's floor is a floor, not a requirement to have asked."""
    return seats is None or seats >= rung.min_seats


def propose_concession(config: AgentConfig, offered: list[str],
                       seats: int | None = None) -> dict:
    """The next rung this call has not used yet.

    `offered` is what the session has already given, so a prospect who pushes three times
    gets three different answers instead of the same one louder. Exhausting the ladder is
    a real outcome, not an error to paper over — it is the moment the call is worth a
    human, and it says so.
    """
    ladder = config.knowledge.concessions
    if not ladder:
        return {"error": "no_data",
                "instruction": "You have nothing to trade. Hold the price, restate the "
                               "per-seat value, and offer to bring in a colleague."}

    given = set(offered)
    for rung in ladder:
        if rung.give in given or not _eligible(rung, seats):
            continue
        return {"give": rung.give, "require": rung.require,
                "remaining": sum(1 for r in ladder
                                 if r.give not in given and r.give != rung.give
                                 and _eligible(r, seats)),
                # Never offer two things at once. A model handed a list will read the list.
                "spoken": _spoken(rung),
                "instruction": "Say the spoken line as written. Do not add anything to "
                               "it, and do not offer the next thing until they have "
                               "answered this one."}

    return {"error": "at_limit", "offered": offered,
            "instruction": "You have given everything you are authorised to give. Do not "
                           "invent a discount and do not repeat an earlier offer. Say "
                           "plainly that you have gone as far as you can on your own, "
                           "and offer to bring in a colleague who can go further."}
