"""FastAPI app: call lifecycle and the dashboard event stream.

Run: uvicorn backend.main:app --reload
"""
import asyncio
import json
import os
import secrets
import time

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

load_dotenv()

from . import agents, agora, console, db, proxy, rtm, state  # noqa: E402  (env first)
from . import tools  # noqa: E402

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """The pool is created lazily on first use, so nothing here has to succeed for the
    keyless text-mode paths to work. Closing it on shutdown is what stops a reload leaking
    connections against a free-tier database with a low connection cap."""
    yield
    await db.close()


app = FastAPI(title="PitchPilot", lifespan=lifespan)
# The widget runs on whatever site embedded it, so the call endpoints are cross-origin by
# design. The allowlist on the agent, not CORS, is what decides who may start a call.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(proxy.router)
app.include_router(console.router)

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
CONSOLE_URL = os.getenv("CONSOLE_URL", "http://localhost:3001")
SESSIONS: dict[str, dict] = {}
AGENT_UID, PROSPECT_UID = "1001", "1002"


class StartCall(BaseModel):
    agent_id: str
    prospect_name: str | None = None
    page_context: str = "pricing"
    # The widget runs in an iframe served by the console, so its own Origin header is
    # always the console — it can never reveal which site embedded it. Phase 4's loader
    # reads location.origin on the host page and passes it down to be checked here.
    # Browser-supplied either way, so this raises the bar on copied snippets rather than
    # authenticating anyone; a signed per-origin token is the real fix if it ever matters.
    page_origin: str | None = None


class StopCall(BaseModel):
    session_id: str



@app.post("/start-call")
async def start_call(req: StartCall, origin: str | None = Header(None)):
    loaded = await agents.load(req.agent_id)
    if loaded is None:
        raise HTTPException(404, "no such agent")
    config, _ = loaded

    allowed = await _allowed_origins(req.agent_id)
    if not agents.allowed_origin(allowed, req.page_origin or origin):
        # Agent ids are public — they sit in the embed snippet — so this is the check that
        # stops a stranger burning the operator's Agora minutes (PRD 6.1).
        raise HTTPException(403, f"origin {req.page_origin or origin!r} is not allowed")

    session_id = f"sess_{secrets.token_hex(2)}"
    channel = rtm.channel_for(session_id)
    await agents.bind(session_id, req.agent_id)

    token = agora.build_token(channel, int(PROSPECT_UID))
    llm_url = f"{PUBLIC_BASE_URL}/v1/chat/completions?session_id={session_id}"
    joined = await agora.join(
        agora.start_payload(config, session_id, channel, token, llm_url, AGENT_UID, PROSPECT_UID))

    agents.set_engine_agent(session_id, joined["agent_id"])
    state.get(session_id)
    if db.DATABASE_URL:
        await db.start_call(session_id, req.agent_id)
    SESSIONS[session_id] = {"engine_agent_id": joined["agent_id"], "agent_id": req.agent_id,
                            "channel": channel, "started": time.time()}
    return {"app_id": agora.APP_ID, "channel": channel, "rtc_token": token, "uid": PROSPECT_UID,
            "session_id": session_id, "engine_agent_id": joined["agent_id"],
            "agent_rtc_uid": AGENT_UID}


@app.post("/stop-call")
async def stop_call(req: StopCall):
    session = SESSIONS.pop(req.session_id, None)
    if not session:
        return {"ok": False, "reason": "unknown session"}

    await agora.leave(session["engine_agent_id"])  # explicit — never rely on idle_timeout
    duration = int(time.time() - session["started"])
    final = state.drop(req.session_id)
    bound = agents.for_session(req.session_id)

    if final and bound:
        _, _, agent_secrets = bound
        tools.sync_contact(agent_secrets, final, force=True)
    if db.DATABASE_URL and final:
        await db.end_call(req.session_id, duration, _outcome(final), final)

    # publish() stamps the owning agent by looking the session up, so the binding has to
    # outlive the last event of the call.
    rtm.publish(req.session_id, "call_ended", {"duration_s": duration})
    agents.release(req.session_id)
    return {"ok": True}


def _outcome(lead: dict) -> str | None:
    """What the call amounted to, for the console's call list (PRD 6.2)."""
    if lead.get("next_action") == "book_demo":
        return "meeting_booked"
    if lead.get("next_action") == "escalate":
        return "escalated"
    return "lead_qualified" if lead.get("qualification") in ("warm", "hot") else None


async def _allowed_origins(agent_id: str) -> list[str]:
    agent = await db.get_agent(agent_id)
    return agent["allowed_origins"] if agent else []


@app.get("/events")
async def events(agent_id: str = ""):
    """Console event stream carrying the PRD 6.2 envelope. EventSource reconnects itself."""
    q = rtm.open_stream()

    async def pump():
        try:
            while True:
                try:
                    owner, msg = await asyncio.wait_for(q.get(), timeout=15)
                    if agent_id and owner != agent_id:
                        continue
                    yield "data: " + json.dumps(msg) + "\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"  # stops proxies closing an idle stream
        finally:
            rtm.close_stream(q)

    return StreamingResponse(pump(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


EMBED_JS = """/* PitchPilot embed loader. The whole integration on a customer's site is the script tag
   that fetched this file (PRD 6.5).

   An iframe rather than an inline widget: style isolation from the host page, no CSP
   negotiation, and the Agora SDK stays off the host's global scope. The cost is that the
   microphone prompt needs the host page on HTTPS with the allow attribute intact.

   The iframe is mounted collapsed to launcher size and resizes on a postMessage from the
   widget, so the host page keeps its bottom-right corner clickable while the widget is
   idle. If that message never arrives the panel size is used, which is wrong-looking but
   never broken. */
(function () {
  var CONSOLE = "__CONSOLE__";
  var script = document.currentScript;
  var agent = new URL(script.src).searchParams.get("agent");
  if (!agent) return console.error("[pitchpilot] embed script has no ?agent= parameter");
  if (document.getElementById("pitchpilot-frame")) return;

  var frame = document.createElement("iframe");
  frame.id = "pitchpilot-frame";
  frame.title = "Talk to sales";
  frame.allow = "microphone";
  // The iframe is served by the console, so its own Origin header always names the
  // console. The host page origin has to be read here and passed down explicitly.
  frame.src = CONSOLE + "/widget?agent=" + encodeURIComponent(agent) +
    "&origin=" + encodeURIComponent(location.origin);
  frame.style.cssText = [
    "position:fixed", "right:20px", "bottom:20px", "z-index:2147483000",
    "border:0", "background:transparent", "color-scheme:normal",
    "width:220px", "height:76px",
    "transition:width .18s ease,height .18s ease"
  ].join(";");

  window.addEventListener("message", function (event) {
    if (new URL(CONSOLE).origin !== event.origin) return;
    var data = event.data;
    if (!data || data.source !== "pitchpilot" || data.type !== "resize") return;
    frame.style.width = Math.round(data.width) + "px";
    frame.style.height = Math.round(data.height) + "px";
  });

  (document.body || document.documentElement).appendChild(frame);
})();
"""


@app.get("/embed.js")
def embed_js():
    """No Subresource Integrity hash on the snippet: the loader is first-party and meant to
    be redeployed, and a pinned hash would break every existing embed on the next deploy
    (PRD 6.5). The allowed-origins check on /start-call is the control on this surface."""
    return PlainTextResponse(
        EMBED_JS.replace("__CONSOLE__", CONSOLE_URL.rstrip("/")),
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=60"},
    )


@app.get("/lead-state/{session_id}")
def lead_state(session_id: str):
    return state.get(session_id)


@app.get("/agents/{agent_id}/pricing")
async def agent_pricing(agent_id: str):
    """Public: the demo site renders its table from the agent's own knowledge, so the page
    and the agent cannot contradict each other (PRD 10.2)."""
    loaded = await agents.load(agent_id)
    if loaded is None:
        raise HTTPException(404, "no such agent")
    config, _ = loaded
    return {"currency": config.knowledge.currency,
            "tiers": [t.model_dump() for t in config.knowledge.tiers]}
