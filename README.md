# PitchPilot

Real-time voice AI sales agent. Agora Conversational AI Engine handles the audio pipeline
(ASR, turn detection, barge-in, TTS); this backend is the brain behind it, exposed as an
OpenAI-compatible custom LLM. See [PRD.md](PRD.md) for the full spec.

## Run

```bash
python -m venv .venv && . .venv/Scripts/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                # fill it in
uvicorn backend.main:app --reload

cd web && npm install && npm run dev
```

The engine calls the proxy over the public internet, so a tunnel is required from day one —
localhost will never work. Point `PUBLIC_BASE_URL` at it and verify with a curl from outside
the LAN before blaming the engine.

## Test the brain without burning voice minutes

Conversational AI minutes are the scarce resource. Everything except integration runs is text:

```bash
curl -N localhost:8000/v1/chat/completions?session_id=t \
  -H 'Content-Type: application/json' \
  -d '{"stream":true,"messages":[{"role":"user","content":"What does it cost for 20 users?"}]}'

python -m backend.scenario_check   # PRD 14 acceptance scenario, scripted LLM, no keys
python backend/state.py           # lead state + BANT scoring
python backend/token2.py          # AccessToken2 packing, pinned to a golden vector
```

`scenario_check` is the Phase 2 gate: it drives the full six-step scenario with a scripted
LLM, so the asserts cover our logic — tool dispatch, the 20 to 200 seat re-quote, BANT
derivation, idempotent booking, the events the dashboard renders — rather than Groq's word
choice. No API keys, under a second to run.

## Layout

```
backend/                 FastAPI — uvicorn backend.main:app --reload  (:8000)
  main.py                /start-call, /stop-call, /pricing, /lead-state/{id}
  proxy.py               /v1/chat/completions — SSE, tool loop, metadata first-chunk
  playbook.py            system prompt assembly (llm.system_messages stays empty)
  state.py               lead state store + BANT scoring
  tools/                 pricing, battlecards, crm, calendar, escalation
  rtm.py                 event publisher (lead_state, tool_call, outcome, escalation, call_ended)
  agora.py               token generation + join/leave/speak
  data/                  pricing.json, battlecards.json
web/                     Next.js (App Router, TS, Tailwind) — npm run dev  (:3000)
  app/page.tsx           landing + pricing table, rendered from the agent's own pricing.json
  app/dashboard/page.tsx lead-state panel + tool-call chips
  app/rep/page.tsx       escalation queue, Join Call
  components/CallWidget  Agora Voice SDK, widget state machine
  lib/                   api client, RTM event types, event subscription
```

`web/next.config.ts` rewrites `/api/*` to the backend, so the browser stays same-origin and
there is no CORS setup and no public API URL to keep in sync. Override with `BACKEND_URL`
in `web/.env.local` when the backend is not on `localhost:8000`.

**Events use SSE, not Agora RTM.** PRD 6.2 specified RTM, but the engine's own transcript
stream is what needs that channel — our lead-state and outcome events are ours alone. `GET
/events` streams the exact 6.2 envelope and the dashboard consumes it with `EventSource`.
Every event still funnels through `rtm.publish()`, so moving to the RTM REST API later is a
change to that one function. Worth confirming with Keshav, since he owns the subscriber.
`window.emit({...})` in the browser console still drives the UI with no backend running.

Integrations are written against the live APIs but key-guarded: with no `CALCOM_API_KEY` or
`HUBSPOT_TOKEN`, `check_slots` offers generated times and CRM writes log instead of POSTing,
so a missing key degrades to a logged outcome rather than a broken call.

`backend/token2.py` builds the Agora AccessToken2 ("007") carrying RTC and RTM privileges in
one token. No PyPI package does — `agora-token-builder` is the legacy 006 format, and an
RTC-only token breaks `enable_rtm`. Its output is pinned byte-for-byte to a golden vector
generated from Agora's own reference implementation.
