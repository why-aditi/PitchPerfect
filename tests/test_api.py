"""HTTP surface: call lifecycle, the event stream, and console auth."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from backend import agents, console, main, playbook, proxy, rtm, state, tools

LOCAL = {"Origin": "http://localhost:3000"}


@pytest.fixture(autouse=True)
def stub_agent_lookup(monkeypatch, config, secrets):
    """The HTTP surface is tested without a database. Production no longer falls back to
    the seed when DATABASE_URL is unset — a misconfigured deployment must fail rather than
    quietly serve the demo agent — so the lookup is stubbed here instead."""
    from backend import agents, db
    from backend.seed import demo_config

    ORIGINS = ["http://localhost:3000", "http://localhost:3001"]

    async def load(agent_id):
        return (demo_config(), secrets) if agent_id == "ag_demo" else None

    async def allowed(agent_id):
        return ORIGINS if agent_id == "ag_demo" else []

    # /start-call reads config, origins and secrets in one query now, so this is the
    # lookup the live path actually makes; load() stays stubbed for the keyless fallback
    # and for /agents/{id}/pricing.
    async def runtime(agent_id):
        return (demo_config(), secrets, ORIGINS) if agent_id == "ag_demo" else None

    monkeypatch.setattr(agents, "load", load)
    monkeypatch.setattr(main, "_allowed_origins", allowed)
    monkeypatch.setattr(db, "get_runtime", runtime)


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
    """Frames published after connect. The stream opens with a snapshot of any call already
    in progress, which these tests are not about, so it is consumed first."""
    async def go():
        stream = (await main.events(agent_id="ag_test")).body_iterator.__aiter__()
        await asyncio.wait_for(stream.__anext__(), 2)          # the mid-call snapshot
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


# --- console observe -------------------------------------------------------------------
# Mints an RTC token for a call already in progress. PRD 6.2 keeps transcripts on the
# engine's data channel, so joining the channel is the only way the live and rep views can
# read one. It hands out credentials, so the guards matter.

OBSERVE = {"agent_id": "ag_demo", "channel": "pitchpilot-8f2a"}


def test_observe_requires_an_operator_session(client):
    console.CONSOLE_PASSWORD = "hunter2"
    assert client.post("/console/observe", json=OBSERVE).status_code == 401


def test_observe_refuses_a_channel_that_is_not_ours(operator):
    """Without the prefix check this endpoint would mint a token for any channel name."""
    r = operator.post("/console/observe", json={"agent_id": "ag_demo", "channel": "someone-elses"})
    assert r.status_code == 400


def test_observe_refuses_a_channel_that_merely_contains_the_prefix(operator):
    r = operator.post("/console/observe",
                      json={"agent_id": "ag_demo", "channel": "evil-pitchpilot-8f2a"})
    assert r.status_code == 400


def test_observe_returns_a_joinable_token(operator, monkeypatch):
    monkeypatch.setattr(main.agora, "build_token", lambda channel, uid, **kw: f"007fake-{uid}")
    body = operator.post("/console/observe", json=OBSERVE).json()
    assert body["channel"] == OBSERVE["channel"]
    assert body["rtc_token"].startswith("007")
    assert body["agent_rtc_uid"] == "1001"


def test_two_operators_watching_one_call_get_different_uids(operator, monkeypatch):
    """Agora drops the earlier holder when a uid joins twice, so a fixed uid here would
    knock the first watcher out of the channel."""
    monkeypatch.setattr(main.agora, "build_token", lambda channel, uid, **kw: "007fake")
    uids = {operator.post("/console/observe", json=OBSERVE).json()["uid"] for _ in range(20)}
    assert len(uids) > 1


def test_observer_uids_never_collide_with_the_fixed_call_uids(operator, monkeypatch):
    monkeypatch.setattr(main.agora, "build_token", lambda channel, uid, **kw: "007fake")
    for _ in range(20):
        assert operator.post("/console/observe", json=OBSERVE).json()["uid"] not in ("1001", "1002")


def test_missing_agora_credentials_say_so_instead_of_500(operator, monkeypatch):
    """The console renders this verbatim; "500" tells an operator nothing they can act on."""
    def unconfigured(channel, uid, **kw):
        raise ValueError("app_id and app_certificate must each be 32 hex characters")

    monkeypatch.setattr(main.agora, "build_token", unconfigured)
    r = operator.post("/console/observe", json=OBSERVE)
    assert r.status_code == 503
    assert "not configured" in r.json()["detail"]


def test_a_failed_hangup_still_closes_the_call(bound, monkeypatch):
    """Agora refusing the leave must not leave the row open: the console would show a call
    that never ends, which is how a real session was orphaned."""
    async def refuse(engine_agent_id):
        raise RuntimeError("Agora leave failed 500")

    monkeypatch.setattr(main.agora, "leave", refuse)
    main.SESSIONS[bound] = {"engine_agent_id": "e1", "agent_id": "ag_test",
                            "channel": "pitchpilot-test", "started": 0}
    assert asyncio.run(main.stop_call(main.StopCall(session_id=bound))) == {"ok": True}
    assert bound not in main.SESSIONS
    assert main.agents.for_session(bound) is None, "the binding is released either way"


def test_a_dashboard_opened_mid_call_sees_the_state_already_gathered(bound):
    """SSE has no replay, so without this a rep taking an escalation would sit on "waiting
    for a call" until the prospect happened to say something new (PRD 15.1 step 6)."""
    state.update(bound, company="Acme", seat_count=200)

    async def go():
        stream = (await main.events(agent_id="ag_test")).body_iterator.__aiter__()
        return json.loads((await asyncio.wait_for(stream.__anext__(), 2))[6:])

    msg = asyncio.run(go())
    assert msg["type"] == "lead_state"
    assert msg["session_id"] == bound
    assert msg["data"]["company"] == "Acme" and msg["data"]["seat_count"] == 200


def test_an_idle_agent_replays_nothing(config, secrets):
    """No call in progress means no snapshot, not an empty one."""
    async def go():
        stream = (await main.events(agent_id="ag_nobody")).body_iterator.__aiter__()
        return await asyncio.wait_for(stream.__anext__(), 17)

    assert asyncio.run(go()).startswith(": keepalive")


def test_the_agent_and_the_prospect_get_their_own_tokens(client, monkeypatch):
    """A token binds the uid it was minted for. Giving the engine the prospect's token made
    it fail to join with only "RTC connection failed" — no greeting, no ASR, no turn."""
    minted, joined = [], {}

    def build_token(channel, uid, expire_s=3600):
        minted.append(uid)
        return f"007tok-{uid}"

    async def fake_join(payload):
        joined.update(payload["properties"])
        return {"agent_id": "engine_1"}

    monkeypatch.setattr(main.agora, "build_token", build_token)
    monkeypatch.setattr(main.agora, "join", fake_join)
    monkeypatch.setattr(main.db, "DATABASE_URL", "")

    body = client.post("/start-call", json={"agent_id": "ag_demo"}, headers=LOCAL).json()

    assert sorted(minted) == [1001, 1002], "one token each, not one shared"
    assert joined["token"] == "007tok-1001", "the engine joins as the agent uid"
    assert joined["agent_rtc_uid"] == "1001"
    assert body["rtc_token"] == "007tok-1002", "the widget joins as the prospect uid"
    assert body["uid"] == "1002"
    assert body["rtc_token"] != joined["token"]


# --- the prospect's timezone ------------------------------------------------------------

def test_the_browsers_timezone_reaches_the_slot_lookup_without_being_asked(bound, monkeypatch):
    """A live call read "Friday at 3:30am" aloud to a prospect in India, because check_slots
    ran in UTC until somebody spent a turn saying otherwise. The browser knew all along."""
    agents.set_timezone(bound, "Asia/Kolkata")
    seen = {}
    monkeypatch.setattr(tools, "check_slots",
                        lambda secrets, **kw: seen.update(kw) or {"slots": []})

    proxy.run_tool(bound, "check_slots", {"days_ahead": 1})
    assert seen["timezone_name"] == "Asia/Kolkata"


def test_a_timezone_the_model_supplies_beats_the_browsers(bound, monkeypatch):
    """The prospect can say they are travelling; the browser cannot know that."""
    agents.set_timezone(bound, "Asia/Kolkata")
    seen = {}
    monkeypatch.setattr(tools, "check_slots",
                        lambda secrets, **kw: seen.update(kw) or {"slots": []})

    proxy.run_tool(bound, "check_slots", {"days_ahead": 1, "timezone_name": "Europe/Berlin"})
    assert seen["timezone_name"] == "Europe/Berlin"


def test_a_call_with_no_timezone_behaves_exactly_as_before(bound, monkeypatch):
    """Nothing is trusted from the browser beyond naming a zone, and a call that sends
    none must not start passing None down into the tool."""
    seen = {}
    monkeypatch.setattr(tools, "check_slots",
                        lambda secrets, **kw: seen.update(kw) or {"slots": []})

    proxy.run_tool(bound, "check_slots", {"days_ahead": 1})
    assert "timezone_name" not in seen


def test_the_prompt_carries_the_prospects_own_clock(config):
    """UTC alone had the model reasoning about "tomorrow" in the wrong day."""
    built = playbook.build(config, state.get("sess_tz"), [], tz_name="Asia/Kolkata")
    volatile = built[1]["content"]
    assert "Asia/Kolkata" in volatile and "where the prospect is" in volatile
    assert "UTC" in volatile, "our own clock still has to be there for the ISO slots"


def test_saving_one_credential_does_not_wipe_the_others(operator, monkeypatch):
    """A live operator lost Cal.com by saving HubSpot, then HubSpot by saving Cal.com, then
    both by saving Notion. The console sends only the fields the operator touched, so every
    absent field arrived as its default and a whole-object write erased it."""
    from backend.models import AgentSecrets

    saved = {"secrets": AgentSecrets(calcom_api_key="cal_live_KEEPME",
                                     calcom_event_type_id="6900272")}

    async def fake_get(agent_id):
        return saved["secrets"]

    async def fake_save(agent_id, secrets):
        saved["secrets"] = secrets

    monkeypatch.setattr(console.db, "get_agent", lambda agent_id: _exists())
    monkeypatch.setattr(console.db, "get_secrets", fake_get)
    monkeypatch.setattr(console.db, "save_secrets", fake_save)

    r = operator.put("/console/agents/ag_demo/secrets", json={"hubspot_token": "pat-NEW"})
    assert r.status_code == 200

    assert saved["secrets"].hubspot_token == "pat-NEW", "the field being saved must be written"
    assert saved["secrets"].calcom_api_key == "cal_live_KEEPME", "an untouched key was wiped"
    assert saved["secrets"].calcom_event_type_id == "6900272"


def test_an_explicit_null_still_clears_a_credential(operator, monkeypatch):
    """Merging must not cost the Remove button: absent means leave alone, null means clear."""
    from backend.models import AgentSecrets

    saved = {"secrets": AgentSecrets(hubspot_token="pat-OLD", calcom_api_key="cal_live_KEEPME")}

    async def fake_get(agent_id):
        return saved["secrets"]

    async def fake_save(agent_id, secrets):
        saved["secrets"] = secrets

    monkeypatch.setattr(console.db, "get_agent", lambda agent_id: _exists())
    monkeypatch.setattr(console.db, "get_secrets", fake_get)
    monkeypatch.setattr(console.db, "save_secrets", fake_save)

    operator.put("/console/agents/ag_demo/secrets", json={"hubspot_token": None})
    assert saved["secrets"].hubspot_token is None, "Remove must still clear the value"
    assert saved["secrets"].calcom_api_key == "cal_live_KEEPME"


async def _exists():
    return {"id": "ag_demo"}


async def _missing():
    return None


def test_credentials_for_an_unknown_agent_are_refused_not_silently_dropped(operator, monkeypatch):
    """get_secrets returns an empty AgentSecrets for an id that does not exist, so the
    merge succeeded, the UPDATE matched no rows, and the operator got a 200 and a "Stored"
    badge for a credential that went nowhere. Its neighbours already 404; this one didn't."""
    monkeypatch.setattr(console.db, "get_agent", lambda agent_id: _missing())
    r = operator.put("/console/agents/ag_nosuchagent/secrets", json={"hubspot_token": "pat-X"})
    assert r.status_code == 404
