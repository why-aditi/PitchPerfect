"""FastAPI app: call lifecycle and the dashboard event stream.

Run: uvicorn backend.main:app --reload
"""
import asyncio
import json
import os
import secrets
import time

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

load_dotenv()

from . import agora, console, proxy, rtm, state  # noqa: E402  (env must load before module constants)
from .tools import crm  # noqa: E402

app = FastAPI(title="PitchPilot")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(proxy.router)
app.include_router(console.router)

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
CONSOLE_URL = os.getenv("CONSOLE_URL", "http://localhost:3001")
SESSIONS: dict[str, dict] = {}
AGENT_UID, PROSPECT_UID = "1001", "1002"


class StartCall(BaseModel):
    prospect_name: str | None = None
    page_context: str = "pricing"
    agent_id: str | None = None


class StopCall(BaseModel):
    session_id: str


async def check_origin(agent_id: str | None, origin: str | None) -> None:
    """PRD 6.5: agent ids are public by necessity — they sit in the embed snippet — so the
    allowed-origins list, not the id, is what stops a stranger burning your Agora minutes.

    A request with no Origin header is same-origin or a curl, and is left alone: the console
    and the text-mode test scripts both call this endpoint directly.
    """
    if not agent_id or origin is None:
        return
    from . import db
    if not db.DATABASE_URL:
        return
    agent = await db.get_agent(agent_id)
    if agent is None:
        raise HTTPException(404, "no such agent")
    allowed = agent["allowed_origins"]
    if allowed and origin not in allowed:
        raise HTTPException(403, f"origin {origin} is not on this agent's allowed list")


@app.post("/start-call")
async def start_call(req: StartCall, request: Request):
    await check_origin(req.agent_id, request.headers.get("origin"))
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
  frame.src = CONSOLE + "/widget?agent=" + encodeURIComponent(agent);
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
