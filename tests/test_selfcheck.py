"""The public URL must land on THIS process (PRD 6.3: the engine calls the proxy over
the public internet).

A live call on 2026-09-03 answered every turn with "give me one moment": the ngrok domain
in PUBLIC_BASE_URL was forwarding to a different machine running the same code. Its
backend had no session bound, returned the fallback line with a 200, and nothing on this
side ever logged a request. A tunnel that answers is not a tunnel that answers *here*, so
/start-call proves it with an instance id before spending a minute of engine time.
"""
import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import main, selfcheck
from backend.models import AgentSecrets as AgentSecretsStub


@pytest.fixture(autouse=True)
def fresh_cache():
    selfcheck._cache.clear()
    yield
    selfcheck._cache.clear()


def test_health_names_this_instance():
    r = TestClient(main.app).get("/health")
    assert r.status_code == 200
    assert r.json()["instance"] == selfcheck.INSTANCE_ID


def fake_transport(body: dict | None, status: int = 200):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body or {})
    return httpx.MockTransport(handler)


def test_a_tunnel_that_lands_here_passes():
    ok = fake_transport({"ok": True, "instance": selfcheck.INSTANCE_ID})
    assert asyncio.run(selfcheck.verify("https://tunnel.test", transport=ok)) is None


def test_a_tunnel_that_lands_on_another_backend_is_named():
    other = fake_transport({"ok": True, "instance": "someone-elses-process"})
    problem = asyncio.run(selfcheck.verify("https://tunnel.test", transport=other))
    assert problem and "another" in problem.lower()


def test_an_unreachable_tunnel_is_named():
    async def handler(request):
        raise httpx.ConnectError("no route")
    problem = asyncio.run(selfcheck.verify("https://tunnel.test",
                                           transport=httpx.MockTransport(handler)))
    assert problem and "reach" in problem.lower()


def test_a_non_json_answer_is_named():
    async def handler(request):
        return httpx.Response(200, text="<html>ngrok interstitial</html>")
    problem = asyncio.run(selfcheck.verify("https://tunnel.test",
                                           transport=httpx.MockTransport(handler)))
    assert problem


def test_loopback_is_skipped_with_a_warning(capsys):
    """localhost never reaches the engine, but it is what the tests and text-mode runs
    use; refusing it here would refuse the test suite."""
    assert asyncio.run(selfcheck.verify("http://localhost:8000")) is None
    assert asyncio.run(selfcheck.verify("http://127.0.0.1:8000")) is None


def test_a_passing_check_is_cached_so_calls_do_not_pay_for_it_twice():
    hits = []

    async def handler(request):
        hits.append(1)
        return httpx.Response(200, json={"ok": True, "instance": selfcheck.INSTANCE_ID})

    t = httpx.MockTransport(handler)
    asyncio.run(selfcheck.verify("https://tunnel.test", transport=t))
    asyncio.run(selfcheck.verify("https://tunnel.test", transport=t))
    assert len(hits) == 1


def test_a_failing_check_is_not_cached():
    hits = []

    async def handler(request):
        hits.append(1)
        return httpx.Response(200, json={"instance": "other"})

    t = httpx.MockTransport(handler)
    asyncio.run(selfcheck.verify("https://tunnel.test", transport=t))
    asyncio.run(selfcheck.verify("https://tunnel.test", transport=t))
    assert len(hits) == 2


def test_start_call_refuses_before_joining_when_the_tunnel_is_wrong(monkeypatch):
    """The refusal has to come before agora.join: a joined agent burns minutes while every
    turn goes to the wrong machine."""
    from backend import agents
    from backend.seed import demo_config
    from tests.test_api import LOCAL  # the origin the stubbed agent allows

    async def load(agent_id):
        return (demo_config(), AgentSecretsStub()) if agent_id == "ag_demo" else None

    async def allowed(agent_id):
        return ["http://localhost:3000"]

    monkeypatch.setattr(agents, "load", load)
    monkeypatch.setattr(main, "_allowed_origins", allowed)
    joined = []

    async def fake_join(payload):
        joined.append(payload)
        return {"agent_id": "engine_1"}

    async def wrong(base_url, **kw):
        return "PUBLIC_BASE_URL reaches another backend"

    monkeypatch.setattr(main.agora, "join", fake_join)
    monkeypatch.setattr(main.selfcheck, "verify", wrong)
    r = TestClient(main.app).post("/start-call", json={"agent_id": "ag_demo"}, headers=LOCAL)
    assert r.status_code == 503
    assert "another backend" in r.json()["detail"]
    assert not joined
