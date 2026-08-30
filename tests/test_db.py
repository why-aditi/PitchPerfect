"""Postgres round trips.

Skipped unless DATABASE_URL points at a reachable database. Everything else in the suite
runs keyless; this is the one file that cannot, because the property that matters most —
that a console read never carries a secret — belongs to the query, not the model.

db keeps one module-level pool, and asyncpg binds a pool to the event loop that created
it. Each test therefore runs its whole body inside a single loop and drops the pool
afterwards, via run(). Two asyncio.run() calls in one test would reuse a pool whose loop
has already closed.

Each test works on its own agent id and deletes it, so this is safe to point at the same
database the demo uses.
"""
import asyncio
import os
import uuid

import pytest
from dotenv import load_dotenv

load_dotenv()

from backend import db  # noqa: E402
from backend.models import AgentConfig, AgentSecrets, Battlecard, Knowledge, Persona, Tier  # noqa: E402

# conftest imports backend.db long before this file runs load_dotenv(), so the module
# constant was read from an empty environment. Only this file opts into the database;
# the rest of the suite stays hermetic and needs no network.
db.DATABASE_URL = os.environ.get("DATABASE_URL", "")


def run(body):
    """Run one async body in its own loop with its own pool."""
    async def go():
        db._pool = None
        try:
            return await body()
        finally:
            await db.close()

    return asyncio.run(go())


def _reachable() -> bool:
    if not db.DATABASE_URL:
        return False
    try:
        run(db.connect)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _reachable(), reason="DATABASE_URL is unset or the database is unreachable")


def new_id() -> str:
    return f"ag_test_{uuid.uuid4().hex[:8]}"


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
    async def body():
        await db.connect()
        await db.connect()   # create-if-not-exists must survive a second run
    run(body)


def test_config_survives_the_round_trip(sample):
    aid = new_id()

    async def body():
        await db.save_agent(aid, "Widgets", sample, ["https://a.test"])
        try:
            return await db.get_agent(aid)
        finally:
            await db.delete_agent(aid)

    agent = run(body)
    assert agent["name"] == "Widgets"
    assert agent["allowed_origins"] == ["https://a.test"]
    assert agent["config"] == sample, "jsonb must not reshape the config"
    assert agent["config"].knowledge.tiers[0].volume_break == {"seats": 50, "per_seat_month": 34}
    assert agent["config"].persona.escalation_seat_threshold == 250


def test_a_console_read_never_carries_a_secret(sample):
    """The whole reason secrets get their own column and their own accessor."""
    aid = new_id()

    async def body():
        await db.save_agent(aid, "Widgets", sample, [])
        await db.save_secrets(aid, AgentSecrets(
            calcom_api_key="cal_live_TESTVALUE", hubspot_token="pat-TESTVALUE",
            slack_webhook_url="https://hooks.example/TESTVALUE"))
        try:
            return await db.get_agent(aid)
        finally:
            await db.delete_agent(aid)

    agent = run(body)
    assert "TESTVALUE" not in str(agent), agent
    assert agent["secrets_set"]["calcom_api_key"] == "set"
    assert agent["secrets_set"]["hubspot_token"] == "set"


def test_the_runtime_accessor_does_return_the_real_values(sample):
    aid = new_id()

    async def body():
        await db.save_agent(aid, "Widgets", sample, [])
        await db.save_secrets(aid, AgentSecrets(calcom_api_key="cal_live_TESTVALUE"))
        try:
            return await db.get_secrets(aid)
        finally:
            await db.delete_agent(aid)

    assert run(body).calcom_api_key == "cal_live_TESTVALUE"


def test_saving_config_does_not_wipe_secrets(sample):
    """The console saves config far more often than secrets. An overwrite here would
    disconnect an operator's CRM without telling them."""
    aid = new_id()

    async def body():
        await db.save_agent(aid, "Widgets", sample, [])
        await db.save_secrets(aid, AgentSecrets(hubspot_token="pat-TESTVALUE"))
        sample.persona.identity = "Sells Widgets, revised."
        await db.save_agent(aid, "Widgets", sample, [])
        try:
            return await db.get_secrets(aid)
        finally:
            await db.delete_agent(aid)

    assert run(body).hubspot_token == "pat-TESTVALUE"


def test_unknown_agent_reads_as_none():
    assert run(lambda: db.get_agent("ag_does_not_exist")) is None


def test_calls_are_recorded_and_listed(sample):
    aid, session = new_id(), f"sess_{uuid.uuid4().hex[:6]}"

    async def body():
        await db.save_agent(aid, "Widgets", sample, [])
        await db.start_call(session, aid)
        await db.end_call(session, 214, "meeting_booked",
                          {"session_id": session, "seat_count": 200})
        try:
            return (await db.calls_for_agent(aid))[0], await db.agent_for_session(session)
        finally:
            await db.delete_agent(aid)

    call, owner = run(body)
    assert call["duration_s"] == 214
    assert call["outcome"] == "meeting_booked"
    assert call["lead_state"] is not None
    assert owner == aid


def test_the_agent_list_counts_calls(sample):
    aid = new_id()

    async def body():
        await db.save_agent(aid, "Widgets", sample, [])
        for _ in range(3):
            await db.start_call(f"sess_{uuid.uuid4().hex[:6]}", aid)
        try:
            return next(r for r in await db.list_agents() if r["id"] == aid)
        finally:
            await db.delete_agent(aid)

    assert run(body)["call_count"] == 3


def test_deleting_an_agent_takes_its_calls_with_it(sample):
    aid, session = new_id(), f"sess_{uuid.uuid4().hex[:6]}"

    async def body():
        await db.save_agent(aid, "Widgets", sample, [])
        await db.start_call(session, aid)
        await db.delete_agent(aid)
        return await db.agent_for_session(session)

    assert run(body) is None, "calls must cascade"


def test_seed_produces_a_usable_demo_agent():
    """python -m backend.seed is a documented setup step, so it has to actually work."""
    from backend.seed import DEMO_ID, demo_config

    async def body():
        await db.save_agent(DEMO_ID, "Vantage demo", demo_config(),
                            ["http://localhost:3000", "http://localhost:3001"])
        return await db.get_agent(DEMO_ID)

    agent = run(body)
    assert [t.name for t in agent["config"].knowledge.tiers] == ["Starter", "Growth", "Enterprise"]
    assert "northbeam" in agent["config"].knowledge.battlecards
    assert "http://localhost:3000" in agent["allowed_origins"]
