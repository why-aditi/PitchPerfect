"""Lead state store + BANT scoring. In-memory, one dict per session (PRD 7)."""

_STORE: dict[str, dict] = {}

_ARRAYS = ("objections_raised", "competitor_mentions", "notes")


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
            state["bant"].update({k: v for k, v in value.items() if k in state["bant"]})
        else:
            state[key] = value
    state["qualification"] = qualify(state["bant"])
    return state


def qualify(bant: dict) -> str:
    total = sum(bant.values())
    return "hot" if total >= 9 else "warm" if total >= 5 else "cold"


def drop(session_id: str) -> dict | None:
    return _STORE.pop(session_id, None)
