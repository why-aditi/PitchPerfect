# PitchPilot

Real-time voice AI sales agent. Agora Conversational AI Engine handles the audio pipeline
(ASR, turn detection, barge-in, TTS); this backend is the brain behind it, exposed as an
OpenAI-compatible custom LLM. See [PRD.md](PRD.md) for the full spec.

Two projects in one repo:

- **`console/`** — build and configure an agent without ever opening the Agora dashboard,
  get an embed snippet, and watch calls live. Port 3001.
- **`web/`** — Vantage, a fictional SaaS. The demo site. It carries the widget by loading
  the embed snippet and nothing else. Port 3000.

Both talk to **`backend/`**, a FastAPI service on port 8000.

## Run

```bash
python -m venv .venv && . .venv/Scripts/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                # fill it in
uvicorn backend.main:app --reload

python -m backend.seed                              # creates agent ag_demo

cd console && npm install && npm run dev            # :3001
cd web && npm install && npm run dev                # :3000
```

The engine calls the proxy over the public internet, so a tunnel is required from day one —
localhost will never work. Point `PUBLIC_BASE_URL` at it and verify with a curl from outside
the LAN before blaming the engine.

## Test without burning voice minutes

Conversational AI minutes are the scarce resource. Everything except integration runs is text:

```bash
python -m backend.scenario_check   # PRD 15.1 acceptance scenario, scripted LLM, no keys
python backend/models.py           # AgentConfig round trip, secret masking
python backend/console.py          # console auth: 401s, forged cookies, masking
python backend/state.py            # lead state + BANT scoring
python backend/token2.py           # AccessToken2 packing, pinned to a golden vector
```

`scenario_check` is the regression net for the whole restructure: it drives the full
six-step scenario with a scripted LLM, so the asserts cover our logic — tool dispatch, the
20 to 200 seat re-quote, BANT derivation, idempotent booking, the events the console
renders — rather than Groq's word choice. No API keys, under a second to run.

## Layout

```
backend/                 FastAPI — uvicorn backend.main:app --reload  (:8000)
  main.py                /start-call, /stop-call, /events, /agents/{id}/pricing
  console.py             /console/* — login and agent CRUD
  proxy.py               /v1/chat/completions — SSE, tool loop
  models.py              AgentConfig, AgentSecrets — the console/runtime contract
  db.py                  asyncpg pool, agent and call queries
  schema.sql             agents, calls
  seed.py                inserts ag_demo from the Vantage data
  playbook.py            system prompt assembly
  state.py               lead state store + BANT scoring
  tools/                 pricing, battlecards, crm, calendar, escalation
  rtm.py                 event publisher
  agora.py               engine payload builder + join/leave/speak
  token2.py              AccessToken2 with RTC + RTM privileges
  data/                  seed pricing.json, battlecards.json
console/                 Next.js  (:3001)
  app/login/             one shared operator password
  app/agents/            agent list
  app/agents/[id]/       editor: Persona · Knowledge · Voice · Integrations · Embed
  app/agents/[id]/live/  lead-state dashboard + tool-call chips
  app/agents/[id]/escalations/
  app/widget/            chrome-free widget the embed iframe loads
  lib/                   api client, event stream, types mirrored from models.py
web/                     Next.js  (:3000) — the Vantage demo site
  app/page.tsx           pricing table + the embed script tag, nothing else
```

Both frontends rewrite `/api/*` to the backend, so the browser stays same-origin. That
matters most in the console, whose session cookie is HttpOnly and same-site. Override with
`BACKEND_URL` when the backend is not on `localhost:8000`.

## Notes

**Secrets.** Per-agent Cal.com, HubSpot and Slack credentials live in the database, are
write-only across the API, and read back as `"set"` — never as the value. One shared
`CONSOLE_PASSWORD` gates every console route, since those routes are the only way to reach
them.

**Origins.** Agent ids are public by necessity — they sit in the embed snippet — so
`/start-call` rejects an `Origin` that is not on the agent's allowed list. That check, not
the id, is what stops a stranger burning your Agora minutes.

**Events use SSE, not Agora RTM.** The engine's own transcript stream is what needs that
channel; lead-state and outcome events are ours alone. `GET /events` streams the exact PRD
6.2 envelope and the console consumes it with `EventSource`. Everything funnels through
`rtm.publish()`, so moving to the RTM REST API later is a change to that one function.

**`backend/token2.py`** builds the Agora AccessToken2 (`007`) carrying RTC and RTM
privileges in one token. No PyPI package does — `agora-token-builder` is the legacy 006
format, and an RTC-only token breaks `enable_rtm`. Its output is pinned byte-for-byte to a
golden vector generated from Agora's own reference implementation.

**Still to do (PRD 14, Phase 2).** The runtime has not been de-globalised yet: the tools
still read `backend/data/*.json` and integration credentials still come from the
environment. `AgentConfig` and the seed exist; wiring them through `tools/`, `playbook.py`,
`agora.py` and `proxy.py` is the next phase.
