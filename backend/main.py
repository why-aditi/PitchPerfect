"""FastAPI app: call lifecycle. Run: uvicorn backend.main:app --reload"""
import os
import secrets
import time

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

from . import agora, proxy, rtm, state  # noqa: E402  (env must load first)
from .tools import crm  # noqa: E402

app = FastAPI(title="PitchPilot")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(proxy.router)

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
    suffix = secrets.token_hex(2)
    session_id, channel = f"sess_{suffix}", f"pitchpilot-{suffix}"
    token = agora.build_token(channel, int(PROSPECT_UID))
    llm_url = f"{PUBLIC_BASE_URL}/v1/chat/completions?session_id={session_id}"
    joined = await agora.join(agora.start_payload(session_id, channel, token, llm_url, AGENT_UID, PROSPECT_UID))

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


@app.get("/lead-state/{session_id}")
def lead_state(session_id: str):
    return state.get(session_id)


@app.get("/pricing")
def pricing():
    """The landing page renders from the same file the agent reads, so they cannot disagree."""
    from .tools.pricing import _DATA
    return _DATA
