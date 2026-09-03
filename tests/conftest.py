"""Shared fixtures.

Most backend modules hold per-call state in module-level dicts, which is right for a
single process serving live calls but means tests must not inherit each other's leftovers.
The autouse fixture below resets every one of them.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import agents, extract, rtm, state  # noqa: E402
from backend.models import AgentConfig, AgentSecrets, Battlecard, Knowledge, Persona, Tier  # noqa: E402
from backend.tools import calendar as cal  # noqa: E402
from backend.tools import crm  # noqa: E402
from backend.tools import notion  # noqa: E402


@pytest.fixture(autouse=True)
def clean_module_state():
    for store in (state._STORE, agents._bound, agents._engine, agents._timezone,
                  cal._booked, crm._last_sync, notion._pages, notion._schemas,
                  extract._running, extract._latest, extract._dirty):
        store.clear()
    rtm._subscribers.clear()
    rtm._queues.clear()
    rtm._loop = None
    # .env may name a real tunnel; the suite must never reach the network to prove it.
    # Loopback is skipped by the self-check, which is the behaviour text-mode runs rely on.
    from backend import main
    main.PUBLIC_BASE_URL = "http://localhost:8000"
    yield
    for store in (state._STORE, agents._bound, agents._engine, agents._timezone,
                  cal._booked, crm._last_sync, notion._pages, notion._schemas):
        store.clear()
    rtm._subscribers.clear()
    rtm._queues.clear()


@pytest.fixture
def config() -> AgentConfig:
    """A small agent, independent of the seed data, so tier-boundary tests stay readable."""
    return AgentConfig(
        persona=Persona(identity="Sells Widgets, a widget platform."),
        knowledge=Knowledge(
            currency="USD",
            tiers=[
                Tier(name="Starter", per_seat_month=19, min_seats=1, max_seats=9,
                     features=["Core"]),
                Tier(name="Growth", per_seat_month=39, min_seats=10, max_seats=99,
                     volume_break={"seats": 50, "per_seat_month": 34}, features=["SSO"]),
                Tier(name="Enterprise", per_seat_month=32, min_seats=100, max_seats=None,
                     volume_break={"seats": 250, "per_seat_month": 27}, features=["SAML"]),
            ],
            battlecards={
                "northbeam": Battlecard(positioning="They report, we act.",
                                        we_win=["Setup time"], we_concede=["Attribution depth"],
                                        proof_point="Kestrel moved 340 seats."),
            },
        ),
    )


@pytest.fixture
def secrets() -> AgentSecrets:
    """No credentials — every integration takes its stub path."""
    return AgentSecrets()


@pytest.fixture
def events() -> list[dict]:
    captured: list[dict] = []
    rtm.subscribe(captured.append)
    return captured


@pytest.fixture
def bound(config, secrets):
    """A session with an agent pinned to it, as /start-call would leave it."""
    sid = "sess_test"
    agents._bound[sid] = ("ag_test", config, secrets)
    return sid
