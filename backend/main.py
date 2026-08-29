"""FastAPI app: call lifecycle and the dashboard event stream.

Run: uvicorn backend.main:app --reload
"""
import asyncio
import json
import os
import secrets
import time

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv()

from . import agora, console, proxy, rtm, state  # noqa: E402  (env must load before module constants)
from .tools import crm  # noqa: E402

app = FastAPI(title="PitchPilot")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(proxy.router)
app.include_router(console.router)

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
SESSIONS: dict[str, dict] = {}
AGENT_UID, PROSPECT_UID = "1001", "1002"


class StartCall(BaseModel):
    prospect_name: str | None = None
    page_context: str = "pricing"


class StopCall(BaseModel):
    session_id: str


@app.post("/start-call")
async def start_call(req: StartCall):
    session_id = f"sess_{secrets.token_hex(2)}"
    channel = rtm.channel_for(session_id)
    token = agora.build_token(channel, int(PROSPECT_UID))
    llm_url = f"{PUBLIC_BASE_URL}/v1/chat/completions?session_id={session_id}"
    joined = await agora.join(
        agora.start_payload(session_id, channel, token, llm_url, AGENT_UID, PROSPECT_UID))

    state.get(session_id)
    SESSIONS[session_id] = {"agent_id": joined["agent_id"], "channel": channel, "started": time.time()}
    return {"app_id": agora.APP_ID, "channel": channel, "rtc_token": token, "uid": PROSPECT_UID,
            "session_id": session_id, "agent_id": joined["agent_id"], "agent_rtc_uid": AGENT_UID}


@app.post("/stop-call")
async def stop_call(req: StopCall):
    session = SESSIONS.pop(req.session_id, None)
    if not session:
        return {"ok": False, "reason": "unknown session"}
    await agora.leave(session["agent_id"])  # explicit leave — never rely on idle_timeout
    final = state.drop(req.session_id)
    if final:
        crm.sync_contact(final, force=True)
    rtm.publish(req.session_id, "call_ended", {"duration_s": int(time.time() - session["started"])})
    return {"ok": True}


@app.get("/events")
async def events():
    """Dashboard event stream carrying the PRD 6.2 envelope. EventSource reconnects itself."""
    q = rtm.open_stream()

    async def pump():
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15)
                    yield "data: " + json.dumps(msg) + "\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"  # stops proxies closing an idle stream
        finally:
            rtm.close_stream(q)

    return StreamingResponse(pump(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/lead-state/{session_id}")
def lead_state(session_id: str):
    return state.get(session_id)


@app.get("/agents/{agent_id}/pricing")
async def agent_pricing(agent_id: str):
    """Public: the demo site renders its table from the agent's own knowledge, so the page
    and the agent cannot contradict each other (PRD 10.2)."""
    from . import db
    from .models import AgentConfig

    config: AgentConfig | None = None
    if db.DATABASE_URL:
        agent = await db.get_agent(agent_id)
        if agent is None:
            raise HTTPException(404, "no such agent")
        config = agent["config"]
    else:
        # ponytail: no database configured yet means serve the seed, so the demo site works
        # before Phase 1 is deployed. Remove once DATABASE_URL is always set.
        from .seed import demo_config
        config = demo_config()

    return {"currency": config.knowledge.currency,
            "tiers": [t.model_dump() for t in config.knowledge.tiers]}
