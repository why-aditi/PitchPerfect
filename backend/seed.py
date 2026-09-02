"""Seeds agent ag_demo from the Vantage data that used to be read at import time.

Run: python -m backend.seed
"""
import asyncio
import json
import os
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


async def seed_secrets() -> list[str]:
    """Optionally move integration credentials from the environment onto the demo agent.

    Credentials live in the database per agent (PRD 17) and are read from nowhere else at
    call time — this only puts them there, so a fresh clone books a real meeting and writes
    a real deal without hand-pasting into the console first. Whatever is already stored is
    kept: env fills in the fields it names and nothing else, so re-seeding never wipes a
    console edit.
    """
    incoming = {"calcom_api_key": os.getenv("CAL_API_KEY"),
                "calcom_event_type_id": os.getenv("CAL_EVENT_TYPE_ID"),
                "hubspot_token": os.getenv("HUBSPOT_TOKEN")}
    filled = {k: v for k, v in incoming.items() if v}
    if not filled:
        return []
    stored = await db.get_secrets(DEMO_ID)
    await db.save_secrets(DEMO_ID, stored.model_copy(update=filled))
    return sorted(filled)


async def main() -> None:
    config = demo_config()
    await db.save_agent(DEMO_ID, "Vantage demo", config,
                        ["http://localhost:3000", "http://localhost:3001"])
    secrets = await seed_secrets()
    agent = await db.get_agent(DEMO_ID)
    print(f"seeded {DEMO_ID}: {len(agent['config'].knowledge.tiers)} tiers, "
          f"{len(agent['config'].knowledge.battlecards)} battlecards, "
          f"origins {agent['allowed_origins']}")
    print(f"secrets: {', '.join(secrets)} from env" if secrets else
          "secrets: nothing in env; set CAL_API_KEY, CAL_EVENT_TYPE_ID and HUBSPOT_TOKEN, "
          "or paste them in the console")
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
