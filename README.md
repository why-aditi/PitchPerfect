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

The engine calls the proxy over the public internet, so a tunnel is required from day one â€”
localhost will never work. Point `PUBLIC_BASE_URL` at it and verify with a curl from outside
the LAN before blaming the engine.

## Test the brain without burning voice minutes

Conversational AI minutes are the scarce resource. Everything except integration runs is text:

```bash
curl -N localhost:8000/v1/chat/completions?session_id=t \
  -H 'Content-Type: application/json' \
  -d '{"stream":true,"messages":[{"role":"user","content":"What does it cost for 20 users?"}]}'

python backend/state.py     # lead state + BANT self-check
```

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

The dashboard and rep view render from `lib/events.ts`, which today is a window hook —
`window.emit({type:"lead_state", ...})` in the console drives the whole UI. Swap its body
for an RTM subscribe on `<channel>-events`; the handler signature does not change.
