"""Seeds agent ag_demo from the Vantage data that used to be read at import time.

Run: python -m backend.seed
"""
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from . import db  # noqa: E402
from .models import AgentConfig, Battlecard, Knowledge, Persona, Tier  # noqa: E402

DEMO_ID = "ag_demo"
DATA = Path(__file__).parent / "data"

IDENTITY = ("You are the AI sales assistant for Vantage, a work management platform. "
            "You are on a live voice call with a prospect.")


def demo_config() -> AgentConfig:
    pricing = json.loads((DATA / "pricing.json").read_text(encoding="utf-8"))
    cards = json.loads((DATA / "battlecards.json").read_text(encoding="utf-8"))
    return AgentConfig(
        persona=Persona(identity=IDENTITY),
        knowledge=Knowledge(
            currency=pricing["currency"],
            tiers=[Tier(**t) for t in pricing["tiers"]],
            battlecards={k: Battlecard(**v) for k, v in cards.items()},
        ),
    )


async def main() -> None:
    config = demo_config()
    await db.save_agent(DEMO_ID, "Vantage demo", config,
                        ["http://localhost:3000", "http://localhost:3001"])
    agent = await db.get_agent(DEMO_ID)
    print(f"seeded {DEMO_ID}: {len(agent['config'].knowledge.tiers)} tiers, "
          f"{len(agent['config'].knowledge.battlecards)} battlecards, "
          f"origins {agent['allowed_origins']}")
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
