"""Postgres round trips.

Skipped unless DATABASE_URL points at a reachable database. Everything else in the suite
runs keyless; this is the one file that cannot, because the property that matters most —
that a console read never carries a secret — is a property of the query, not of the model.

Each test works on its own agent id and deletes it afterwards, so this is safe to run
against the same database the demo uses.
"""
import asyncio
import os
import uuid

import pytest
from dotenv import load_dotenv

load_dotenv()

from backend import db  # noqa: E402
from backend.models import AgentConfig, AgentSecrets, Battlecard, Knowledge, Persona, Tier  # noqa: E402


def _reachable() -> bool:
    if not db.DATABASE_URL:
        return False
    try:
        asyncio.run(db.connect())
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _reachable(), reason="DATABASE_URL is unset or the database is unreachable")


@pytest.fixture
def agent_id():
    aid = f"ag_test_{uuid.uuid4().hex[:8]}"
    yield aid
    asyncio.run(db.delete_agent(aid))


@pytest.fixture
def sample() -> AgentConfig:
    return AgentConfig(
        persona=Persona(identity="Sells Widgets.", escalation_seat_threshold=250),
        knowledge=Knowledge(
            tiers=[Tier(name="Growth", per_seat_month=39, min_seats=10, max_seats=99,
                        volume_break={"seats": 50, "per_seat_month": 34}, features=["SSO"])],
            battlecards={"northbeam": Battlecard(positioning="They report, we act.",
                                                 we_win=["Setup"], we_concede=["Depth"],
                                                 proof_point="Kestrel.")},
        ),
    )


def test_schema_applies_and_is_idempotent():
    asyncio.run(db.connect())
    asyncio.run(db.connect())  # create-if-not-exists must not fail on a second run


def test_config_survives_the_round_trip(agent_id, sample):
    asyncio.run(db.save_agent(agent_id, "Widgets", sample, ["https://a.test"]))
    agent = asyncio.run(db.get_agent(agent_id))

    assert agent["name"] == "Widgets"
    assert agent["allowed_origins"] == ["https://a.test"]
    assert agent["config"] == sample, "jsonb must not reshape the config"
    assert agent["config"].knowledge.tiers[0].volume_break == {"seats": 50, "per_seat_month": 34}
    assert agent["config"].persona.escalation_seat_threshold == 250


def test_a_console_read_never_carries_a_secret(agent_id, sample):
    """The whole reason secrets live in their own column and their own accessor."""
    asyncio.run(db.save_agent(agent_id, "Widgets", sample, []))
    asyncio.run(db.save_secrets(agent_id, AgentSecrets(
        calcom_api_key="cal_live_TESTVALUE", hubspot_token="pat-TESTVALUE",
        slack_webhook_url="https://hooks.example/TESTVALUE")))

    agent = asyncio.run(db.get_agent(agent_id))
    assert "TESTVALUE" not in str(agent), agent
    assert agent["secrets_set"]["calcom_api_key"] == "set"
    assert agent["secrets_set"]["hubspot_token"] == "set"


def test_the_runtime_accessor_does_return_the_real_values(agent_id, sample):
    asyncio.run(db.save_agent(agent_id, "Widgets", sample, []))
    asyncio.run(db.save_secrets(agent_id, AgentSecrets(calcom_api_key="cal_live_TESTVALUE")))
    assert asyncio.run(db.get_secrets(agent_id)).calcom_api_key == "cal_live_TESTVALUE"


def test_saving_config_does_not_wipe_secrets(agent_id, sample):
    """The console saves config far more often than secrets; an overwrite here would log
    an operator out of their own CRM without telling them."""
    asyncio.run(db.save_agent(agent_id, "Widgets", sample, []))
    asyncio.run(db.save_secrets(agent_id, AgentSecrets(hubspot_token="pat-TESTVALUE")))
    sample.persona.identity = "Sells Widgets, revised."
    asyncio.run(db.save_agent(agent_id, "Widgets", sample, []))
    assert asyncio.run(db.get_secrets(agent_id)).hubspot_token == "pat-TESTVALUE"


def test_unknown_agent_reads_as_none():
    assert asyncio.run(db.get_agent("ag_does_not_exist")) is None


def test_calls_are_recorded_and_listed(agent_id, sample):
    asyncio.run(db.save_agent(agent_id, "Widgets", sample, []))
    session = f"sess_{uuid.uuid4().hex[:6]}"
    asyncio.run(db.start_call(session, agent_id))
    asyncio.run(db.end_call(session, 214, "meeting_booked",
                            {"session_id": session, "seat_count": 200}))

    call = asyncio.run(db.calls_for_agent(agent_id))[0]
    assert call["duration_s"] == 214
    assert call["outcome"] == "meeting_booked"
    assert call["lead_state"] is not None
    assert asyncio.run(db.agent_for_session(session)) == agent_id


def test_the_agent_list_counts_calls(agent_id, sample):
    asyncio.run(db.save_agent(agent_id, "Widgets", sample, []))
    for _ in range(3):
        asyncio.run(db.start_call(f"sess_{uuid.uuid4().hex[:6]}", agent_id))
    row = next(r for r in asyncio.run(db.list_agents()) if r["id"] == agent_id)
    assert row["call_count"] == 3


def test_deleting_an_agent_takes_its_calls_with_it(sample):
    aid = f"ag_test_{uuid.uuid4().hex[:8]}"
    session = f"sess_{uuid.uuid4().hex[:6]}"
    asyncio.run(db.save_agent(aid, "Widgets", sample, []))
    asyncio.run(db.start_call(session, aid))
    asyncio.run(db.delete_agent(aid))
    assert asyncio.run(db.agent_for_session(session)) is None, "calls must cascade"


def test_seed_produces_a_usable_demo_agent():
    """python -m backend.seed is a documented setup step, so it has to actually work."""
    from backend.seed import DEMO_ID, demo_config

    asyncio.run(db.save_agent(DEMO_ID, "Vantage demo", demo_config(),
                              ["http://localhost:3000", "http://localhost:3001"]))
    agent = asyncio.run(db.get_agent(DEMO_ID))
    assert [t.name for t in agent["config"].knowledge.tiers] == ["Starter", "Growth", "Enterprise"]
    assert "northbeam" in agent["config"].knowledge.battlecards
    assert "http://localhost:3000" in agent["allowed_origins"]
