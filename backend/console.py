"""Operator console API: one shared password, agent CRUD.

No user table and no registration. The password gates every route here because these
routes are the only way to read and write integration credentials.
"""
import hmac
import os
import secrets as pysecrets

from fastapi import APIRouter, Cookie, HTTPException, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel

from . import db
from .models import AgentConfig, AgentSecrets

router = APIRouter(prefix="/console")

CONSOLE_PASSWORD = os.getenv("CONSOLE_PASSWORD", "")
SESSION_SECRET = os.getenv("CONSOLE_SESSION_SECRET", "")
SESSION_MAX_AGE = 60 * 60 * 12
COOKIE = "pp_console"

_serializer = URLSafeTimedSerializer(SESSION_SECRET or pysecrets.token_hex(32), salt="console")


class Login(BaseModel):
    password: str


class AgentWrite(BaseModel):
    name: str
    config: AgentConfig
    allowed_origins: list[str] = []


def require_session(session: str | None) -> None:
    """Raises 401 unless the cookie is a valid, unexpired session."""
    if not CONSOLE_PASSWORD:
        raise HTTPException(500, "CONSOLE_PASSWORD is not set; the console is unusable")
    if not session:
        raise HTTPException(401, "not signed in")
    try:
        _serializer.loads(session, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "session expired") from None


@router.post("/login")
def login(body: Login, response: Response):
    if not CONSOLE_PASSWORD:
        raise HTTPException(500, "CONSOLE_PASSWORD is not set")
    # Constant time: a timing side channel on a single shared password is worth avoiding.
    if not hmac.compare_digest(body.password, CONSOLE_PASSWORD):
        raise HTTPException(401, "wrong password")
    response.set_cookie(COOKIE, _serializer.dumps("operator"), httponly=True,
                        samesite="lax", max_age=SESSION_MAX_AGE)
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/agents")
async def agents(pp_console: str | None = Cookie(None)):
    require_session(pp_console)
    return await db.list_agents()


@router.post("/agents")
async def create_agent(body: AgentWrite, pp_console: str | None = Cookie(None)):
    require_session(pp_console)
    agent_id = f"ag_{pysecrets.token_hex(3)}"
    await db.save_agent(agent_id, body.name, body.config, body.allowed_origins)
    return {"id": agent_id}


@router.get("/agents/{agent_id}")
async def read_agent(agent_id: str, pp_console: str | None = Cookie(None)):
    require_session(pp_console)
    agent = await db.get_agent(agent_id)
    if agent is None:
        raise HTTPException(404, "no such agent")
    return agent  # get_agent returns masked secrets only


@router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, body: AgentWrite, pp_console: str | None = Cookie(None)):
    require_session(pp_console)
    if await db.get_agent(agent_id) is None:
        raise HTTPException(404, "no such agent")
    await db.save_agent(agent_id, body.name, body.config, body.allowed_origins)
    return {"ok": True}


@router.put("/agents/{agent_id}/secrets")
async def update_secrets(agent_id: str, body: AgentSecrets,
                         pp_console: str | None = Cookie(None)):
    require_session(pp_console)
    await db.save_secrets(agent_id, body)
    return body.masked()  # echo the mask, never the values just written


@router.delete("/agents/{agent_id}")
async def remove_agent(agent_id: str, pp_console: str | None = Cookie(None)):
    require_session(pp_console)
    await db.delete_agent(agent_id)
    return {"ok": True}


@router.get("/agents/{agent_id}/calls")
async def agent_calls(agent_id: str, pp_console: str | None = Cookie(None)):
    require_session(pp_console)
    return await db.calls_for_agent(agent_id)


if __name__ == "__main__":
    # Auth and masking are the security-critical parts and need no database.
    import fastapi
    from fastapi.testclient import TestClient

    CONSOLE_PASSWORD = "hunter2"
    app = fastapi.FastAPI()
    app.include_router(router)
    c = TestClient(app)

    # Route-level: an unauthenticated call is refused before any handler work happens.
    assert c.get("/console/agents").status_code == 401, "unauthenticated read must be refused"
    assert c.post("/console/login", json={"password": "wrong"}).status_code == 401
    assert c.get("/console/agents").status_code == 401, "a failed login must not set a session"

    assert c.post("/console/login", json={"password": "hunter2"}).status_code == 200
    cookie = c.cookies.get(COOKIE)
    assert cookie, "login must set the session cookie"

    # Guard-level, so the check needs no database behind the protected routes.
    require_session(cookie)
    for bad in (None, "", "not.a.real.signature", cookie[:-4] + "aaaa"):
        try:
            require_session(bad)
        except HTTPException:
            continue
        raise AssertionError(f"require_session accepted {bad!r}")

    written = AgentSecrets(calcom_api_key="cal_live_secret", slack_webhook_url="https://hook")
    assert "cal_live_secret" not in str(written.masked())
    print("console.py ok")
