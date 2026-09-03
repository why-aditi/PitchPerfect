"""Operator console API: one shared password, agent CRUD.

No user table and no registration. The password gates every route here because these
routes are the only way to read and write integration credentials.
"""
import asyncio
import hmac
import os
import secrets as pysecrets

from fastapi import APIRouter, Cookie, HTTPException, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel

from . import db
from .models import AgentConfig, AgentSecrets
from .tools import notion

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


class Observe(BaseModel):
    agent_id: str
    channel: str


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


@router.post("/agents/{agent_id}/import-tiers")
async def import_tiers(agent_id: str, pp_console: str | None = Cookie(None)):
    """Read the agent's Notion pricing database and hand the tiers back for review.

    Deliberately does not save. An import that wrote straight to the config would wipe
    volume breaks tuned in the editor with rows Notion has no column for, and the
    operator would find out on a live call. This returns a proposal; the ordinary save
    on the Knowledge tab is still what commits it.
    """
    require_session(pp_console)
    if await db.get_agent(agent_id) is None:
        raise HTTPException(404, "no such agent")

    secrets = await db.get_secrets(agent_id)
    # httpx here is synchronous and Notion is two round trips before the query, so this
    # would hold the console's event loop for as long as Notion is slow.
    tiers, note = await asyncio.to_thread(notion.fetch_tiers, secrets)
    if not tiers:
        raise HTTPException(422, note or "Nothing to import.")
    return {"tiers": [t.model_dump() for t in tiers], "note": note}


@router.delete("/agents/{agent_id}")
async def remove_agent(agent_id: str, pp_console: str | None = Cookie(None)):
    require_session(pp_console)
    await db.delete_agent(agent_id)
    return {"ok": True}


@router.post("/observe")
async def observe(body: Observe, pp_console: str | None = Cookie(None)):
    """An RTC token for a channel that is already running, so the console can join a call
    without placing one.

    PRD 6.2 keeps transcripts on the engine's data channel and forbids the backend from
    republishing them, so the live and rep views can only read a transcript by being in the
    channel. Operator-gated, and a fresh uid every time: two operators watching the same
    call must not collide on one uid, which would drop the first out of the channel.
    """
    require_session(pp_console)
    from . import agora, rtm

    if not body.channel.startswith(rtm.CHANNEL_PREFIX):
        raise HTTPException(400, "not a PitchPilot channel")

    uid = pysecrets.randbelow(900_000) + 100_000  # well clear of the fixed 1001/1002
    try:
        token = agora.build_token(body.channel, uid)
    except ValueError as e:
        # Missing or malformed Agora credentials are a deployment problem, not a bug in the
        # request. Saying so is worth a branch: the console renders this message verbatim,
        # and "500" in the live view tells an operator nothing they can act on.
        raise HTTPException(503, f"Agora credentials are not configured: {e}") from None
    return {"app_id": agora.APP_ID, "channel": body.channel,
            "rtc_token": token, "uid": str(uid),
            "session_id": "", "agent_id": "", "agent_rtc_uid": "1001"}


@router.get("/agents/{agent_id}/calls")
async def agent_calls(agent_id: str, pp_console: str | None = Cookie(None)):
    require_session(pp_console)
    return await db.calls_for_agent(agent_id)
