"""Competitor claims come from the agent's own knowledge, or not at all."""
from ..models import AgentConfig


def get_battlecard(config: AgentConfig, competitor: str) -> dict:
    card = config.knowledge.battlecards.get(competitor.strip().lower())
    if not card:
        # The model must surface this, not paper over it (PRD 8).
        return {"error": "no_data", "competitor": competitor,
                "instruction": "Say plainly that you don't have data on them and offer to follow up."}
    return {"competitor": competitor, **card.model_dump()}
