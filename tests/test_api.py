"""HTTP surface: call lifecycle, the event stream, and console auth."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from backend import agents, console, main, proxy, rtm, state

LOCAL = {"Origin": "http://localhost:3000"}


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def operator(client):
    console.CONSOLE_PASSWORD = "hunter2"
    client.post("/console/login", json={"password": "hunter2"})
    return client


# --- start-call guards -----------------------------------------------------------------
# Every one of these must be refused before any Agora call is made, since there are no
# credentials in the test environment and a leaked call would fail loudly instead.

def test_unknown_agent_is_404(client):
    assert client.post("/start-call", json={"agent_id": "ag_nope"}, headers=LOCAL).status_code == 404


def test_disallowed_origin_is_403(client):
    r = client.post("/start-call", json={"agent_id": "ag_demo"},
                    headers={"Origin": "https://evil.test"})
    assert r.status_code == 403


def test_missing_origin_is_403(client):
    """A missing Origin is not a pass."""
    assert client.post("/start-call", json={"agent_id": "ag_demo"}).status_code == 403


def test_a_forwarded_page_origin_is_checked_too(client):
    """The loader forwards the host page's origin; it must be validated, not trusted."""
    r = client.post("/start-call",
                    json={"agent_id": "ag_demo", "page_origin": "https://evil.test"},
                    headers=LOCAL)
    assert r.status_code == 403


def test_a_lookalike_origin_does_not_match(client):
    r = client.post("/start-call", json={"agent_id": "ag_demo"},
                    headers={"Origin": "http://localhost:3000.evil.test"})
    assert r.status_code == 403


def test_agent_id_is_required(client):
    assert client.post("/start-call", json={}, headers=LOCAL).status_code == 422


def test_stop_call_on_an_unknown_session_is_not_an_error(client):
    assert client.post("/stop-call", json={"session_id": "sess_nope"}).json() == \
        {"ok": False, "reason": "unknown session"}


# --- public read -----------------------------------------------------------------------

def test_pricing_is_public_and_matches_the_agent(client):
    body = client.get("/agents/ag_demo/pricing").json()
    assert [t["name"] for t in body["tiers"]] == ["Starter", "Growth", "Enterprise"]
    assert body["currency"] == "USD"


def test_pricing_for_an_unknown_agent_is_404(client):
    assert client.get("/agents/ag_nope/pricing").status_code == 404


# --- outcome derivation ----------------------------------------------------------------

@pytest.mark.parametrize(
    ("lead", "expected"),
    [
        ({"next_action": "book_demo", "qualification": "cold"}, "meeting_booked"),
        ({"next_action": "escalate", "qualification": "cold"}, "escalated"),
        ({"next_action": None, "qualification": "hot"}, "lead_qualified"),
        ({"next_action": None, "qualification": "warm"}, "lead_qualified"),
        ({"next_action": None, "qualification": "cold"}, None),
    ],
)
def test_outcome_reflects_what_the_call_amounted_to(lead, expected):
    assert main._outcome(lead) == expected


# --- event stream ----------------------------------------------------------------------

def read_frames(count: int, publish) -> list[dict]:
    async def go():
        stream = (await main.events(agent_id="ag_test")).body_iterator.__aiter__()
        publish()
        frames = [await asyncio.wait_for(stream.__anext__(), 2) for _ in range(count)]
        return [json.loads(f[6:]) for f in frames]

    return asyncio.run(go())


def test_events_carry_the_prd_envelope(bound):
    msgs = read_frames(2, lambda: proxy.run_tool(bound, "update_lead_state", {"seat_count": 200}))
    assert set(msgs[0]) == {"type", "session_id", "ts", "data"}
    assert msgs[0]["type"] == "lead_state"
    assert msgs[0]["session_id"] == bound


def test_events_are_scoped_to_their_agent(bound, config, secrets):
    """A second agent's call must not appear on this agent's dashboard."""
    agents._bound["sess_other"] = ("ag_other", config, secrets)
    msgs = read_frames(1, lambda: (
        proxy.run_tool("sess_other", "get_pricing", {"seats": 10}),
        proxy.run_tool(bound, "get_pricing", {"seats": 20}),
    ))
    assert msgs[0]["session_id"] == bound


def test_call_ended_reaches_the_dashboard(bound):
    """The console shows a call as finished only if this event survives the agent filter."""
    msgs = read_frames(1, lambda: rtm.publish(bound, "call_ended", {"duration_s": 42}))
    assert msgs[0]["type"] == "call_ended"


def test_a_slow_dashboard_never_stalls_a_call(bound):
    """A console tab that stopped reading must be dropped, not allowed to block a tool call."""
    q = rtm.open_stream()
    for _ in range(q.maxsize + 5):
        rtm.publish(bound, "tool_call", {"name": "x", "args": {}, "result_summary": "y"})
    assert q not in rtm._queues


# --- console auth ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "route",
    ["/console/agents", "/console/agents/ag_demo", "/console/agents/ag_demo/calls"],
)
def test_console_reads_require_a_session(client, route):
    console.CONSOLE_PASSWORD = "hunter2"
    assert client.get(route).status_code == 401


def test_wrong_password_is_refused_and_sets_no_session(client):
    console.CONSOLE_PASSWORD = "hunter2"
    assert client.post("/console/login", json={"password": "nope"}).status_code == 401
    assert client.get("/console/agents").status_code == 401


def test_login_sets_an_httponly_cookie(client):
    console.CONSOLE_PASSWORD = "hunter2"
    r = client.post("/console/login", json={"password": "hunter2"})
    assert r.status_code == 200
    assert "httponly" in r.headers["set-cookie"].lower()


def test_a_tampered_cookie_is_refused(client):
    console.CONSOLE_PASSWORD = "hunter2"
    client.post("/console/login", json={"password": "hunter2"})
    good = client.cookies[console.COOKIE]
    client.cookies.set(console.COOKIE, good[:-4] + "aaaa")
    assert client.get("/console/agents").status_code == 401


def test_an_expired_session_is_refused(client):
    console.CONSOLE_PASSWORD = "hunter2"
    client.post("/console/login", json={"password": "hunter2"})
    cookie = client.cookies[console.COOKIE]
    original, console.SESSION_MAX_AGE = console.SESSION_MAX_AGE, -1
    try:
        with pytest.raises(Exception):
            console.require_session(cookie)
    finally:
        console.SESSION_MAX_AGE = original


def test_console_is_unusable_rather_than_open_when_no_password_is_set(client):
    """Failing closed matters: these routes are the only way to reach stored credentials."""
    original, console.CONSOLE_PASSWORD = console.CONSOLE_PASSWORD, ""
    try:
        assert client.get("/console/agents").status_code == 500
        assert client.post("/console/login", json={"password": ""}).status_code == 500
    finally:
        console.CONSOLE_PASSWORD = original


def test_logout_clears_the_session(operator):
    operator.post("/console/logout")
    assert operator.get("/console/agents").status_code == 401


def test_stop_call_emits_call_ended_that_the_dashboard_can_see(bound, monkeypatch):
    """The agent filter resolves session -> agent from the live binding, so anything
    published after the binding is released is invisible to the console."""
    async def no_leave(engine_agent_id):
        return None

    monkeypatch.setattr(main.agora, "leave", no_leave)
    main.SESSIONS[bound] = {"engine_agent_id": "e1", "agent_id": "ag_test",
                            "channel": "pitchpilot-test", "started": 0}

    async def go():
        stream = (await main.events(agent_id="ag_test")).body_iterator.__aiter__()
        await main.stop_call(main.StopCall(session_id=bound))
        frame = await asyncio.wait_for(stream.__anext__(), 2)
        return json.loads(frame[6:])

    msg = asyncio.run(go())
    assert msg["type"] == "call_ended", msg
