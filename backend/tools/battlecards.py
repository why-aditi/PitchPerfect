import json
from pathlib import Path

_DATA = json.loads((Path(__file__).parent.parent / "data" / "battlecards.json").read_text())


def get_battlecard(competitor: str) -> dict:
    card = _DATA.get(competitor.strip().lower())
    if not card:
        # The model must surface this, not paper over it (PRD 8).
        return {"error": "no_data", "competitor": competitor,
                "instruction": "Say plainly that you don't have data on them and offer to follow up."}
    return {"competitor": competitor, **card}
