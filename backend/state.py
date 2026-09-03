"""Lead state store + BANT scoring. In-memory, one dict per session (PRD 7)."""

_STORE: dict[str, dict] = {}

# Both halves are required for a field to exist: update() skips any key not already in
# the state dict, so a field added to _ARRAYS but not to new_state is dropped silently —
# no error, no log line, just a value that never appears.
_ARRAYS = ("objections_raised", "competitor_mentions", "notes", "concessions_offered")
_INTS = ("seat_count",)


def _as_int(value) -> int | None:
    """A number, or None if what arrived cannot be one.

    Models send numbers as strings often enough that it cannot be fatal: a live call had
    ministral-8b return BANT scores as "2", which made max("2", 0) raise and burned every
    tool hop in the turn on a retry loop that ended in a spurious escalation.
    """
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def new_state(session_id: str) -> dict:
    return {
        "session_id": session_id,
        "company": None,
        "email": None,
        "industry": None,
        "use_case": None,
        "seat_count": None,
        "budget_signal": None,
        "timeline": None,
        "objections_raised": [],
        "competitor_mentions": [],
        # Written by the dispatcher when propose_concession fires, never by the model.
        # It is the record of what this call actually committed to, so the rep who picks
        # up an escalation inherits the promises rather than having to ask.
        "concessions_offered": [],
        "bant": {"budget": 0, "authority": 0, "need": 0, "timeline": 0},
        "qualification": "cold",
        "next_action": None,
        "notes": [],
    }


def get(session_id: str) -> dict:
    return _STORE.setdefault(session_id, new_state(session_id))


def update(session_id: str, **fields) -> dict:
    """Merge fields in. Arrays append without duplicates; bant merges per key."""
    state = get(session_id)
    for key, value in fields.items():
        if value is None or key not in state:
            continue
        if key in _ARRAYS:
            for item in (value if isinstance(value, list) else [value]):
                if item not in state[key]:
                    state[key].append(item)
        elif key == "bant":
            if not isinstance(value, dict):
                continue
            scored = {k: _as_int(v) for k, v in value.items() if k in state["bant"]}
            # Clamped, not just coerced: the schema says 0-3 and a model that reads it as a
            # percentage would otherwise pin qualification to hot for the rest of the call.
            state["bant"].update({k: max(0, min(3, v)) for k, v in scored.items()
                                  if v is not None})
        elif key in _INTS:
            number = _as_int(value)
            if number is not None:
                state[key] = number
        else:
            state[key] = value
    # The derived scores are a floor, never a ceiling: the model sees the conversation and
    # may score higher than the recorded signals prove, and that judgement is kept. The
    # floor only ever raises a score, so evidence accumulates across a call.
    derived = derive_bant(state)
    state["bant"] = {k: max(v, derived[k]) for k, v in state["bant"].items()}
    state["qualification"] = qualify(state["bant"])
    return state


_BUDGET_SCORE = {"under_budget": 3, "stretch": 2, "over_budget": 1}
_TIMELINE_SCORE = {"now": 3, "this_quarter": 2, "exploring": 1}


def derive_bant(state: dict) -> dict:
    """Floor scores from what the call has actually established.

    Left to itself the model fills the other fields reliably and almost never scores BANT,
    so qualification stayed cold on calls that booked a demo. Anything the conversation has
    already proved is scored here instead of asked for twice; authority has no such signal,
    so it stays the model's judgement to make.
    """
    need = 0
    if state.get("seat_count"):
        need = 2
    if state.get("use_case") or state.get("competitor_mentions"):
        need = 3 if need else 2      # comparing vendors is an active evaluation

    budget = _BUDGET_SCORE.get(state.get("budget_signal"), 0)
    if "pricing" in state.get("objections_raised", []):
        budget = max(budget, 1)      # they pushed back on price, so a budget exists

    timeline = _TIMELINE_SCORE.get(state.get("timeline"), 0)
    if state.get("next_action") == "book_demo":
        timeline = max(timeline, 2)  # they agreed to a date, which is the strongest signal

    return {"budget": budget, "authority": 0, "need": need, "timeline": timeline}


def qualify(bant: dict) -> str:
    total = sum(bant.values())
    return "hot" if total >= 9 else "warm" if total >= 5 else "cold"


def drop(session_id: str) -> dict | None:
    return _STORE.pop(session_id, None)
