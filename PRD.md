# PitchPilot — Product Requirements Document

**Team:** Hecker (Aditi Kala, Keshav Sharma)
**Track:** Adaptive AI Sales and Negotiation Agent — EchoSphere 2026
**Status:** Draft for build round — revised 29 Aug 2026 to split into two projects
**Owner of this doc:** Aditi

> Agora API details in this document were verified against `docs.agora.io` (Conversational AI Engine REST reference and the custom-LLM guide) on 29 Aug 2026. Where a field is deprecated, the current replacement is used and the old name is noted.

---

## 1. Summary

PitchPilot is a real-time voice AI sales agent that a prospect talks to in the browser. They can interrupt, compare competitors, object on price, and change requirements mid-call. The agent qualifies them, answers from real pricing and battlecard data, and drives the call to a concrete outcome: a booked demo, a qualified lead in the CRM, or a warm hand-off to a human rep who joins the same live call.

There is no call script anywhere in the system. The agent reasons every turn over a structured lead-state object it maintains through tool calls, plus a sales playbook assembled from the agent's configuration.

The repo holds **two projects**:

**Project 1 — the console** (`console/`). Where an agent is built. You fill in a persona, a goal hierarchy, objection strategies, the pricing tiers and battlecards it may quote from, which tools it may call, and which calendar and CRM it writes to. You never open the Agora dashboard — the console generates the Conversational AI Engine payload for you. Saving an agent yields an embed snippet that drops the voice widget onto any website. The console is also the live surface: lead-state dashboard and rep escalation view, scoped per agent.

**Project 2 — the demo SPA** (`web/`). Vantage, a fictional work-management SaaS with a real-looking pricing page. It carries the "Talk to Sales" widget by loading the embed snippet the console generated, not by bundling its own widget. The demo therefore exercises the same path a real customer would.

## 2. Goals

| # | Goal | How we know it's met |
|---|---|---|
| G1 | Natural turn-taking with true barge-in | Agent stops speaking within ~300 ms of the prospect starting, and its next reply reflects what was said, not what it was about to say |
| G2 | Session memory that propagates | A mid-call change from 20 to 200 seats changes the very next quote, with no restart and no re-asking |
| G3 | Grounded answers | Every price, feature and calendar slot in a transcript traces to a tool call, not model memory |
| G4 | Adaptive objection handling | Pricing, trust and product objections each get a distinct strategy, chosen at runtime |
| G5 | Concrete outcome per call | Call ends with a booking, a qualified CRM record, or an escalation, never a dead end |
| G6 | Escalation with context | Human rep joins the same channel and has a written summary before they speak |
| G7 | An agent is built without touching Agora | An operator configures persona, knowledge, voice and integrations in the console; the engine payload is generated, never hand-edited |
| G8 | One snippet embeds anywhere | A single script tag on an unrelated site produces a working voice call, with no build step on the host page |

## 3. Non-goals

- **Outbound / PSTN calling.** Browser-to-agent only. SIP telephony via Conversational AI Studio is post-hackathon.
- **Per-operator Agora accounts.** One set of platform Agora credentials serves every agent. Bring-your-own credentials is a schema field we leave room for, not a feature we build.
- **Billing, quotas, usage metering.** No plan tiers, no per-agent minute caps.
- **Model training or fine-tuning.** All hosted APIs, no GPU.
- **RAG over long documents.** Agent knowledge is small structured data entered in the console. Document upload is a stretch goal only.
- **Prospect authentication.** The person talking to the widget never logs in. The console operator does.
- **Agent versioning or rollback.** Editing an agent overwrites it. No draft/publish split, no history.
- **Mobile-native app.** Responsive web is enough.

## 4. Users

**Prospect (primary).** On the pricing page, has a question, does not want a form or a callback in three days. Wants an answer now and will interrupt if the agent rambles.

**Operator (new, primary).** Builds and tunes the agent in the console. Knows their own product and sales motion; does not know or care what a turn-detection payload is. Wants to change the escalation threshold and see it take effect on the next call.

**Sales rep (secondary).** Watches the console's live view, gets pulled into calls that need a human. Wants context before speaking, not after.

**Evaluator (tertiary).** Needs to see the adaptive behaviour actually happen — the visible lead state is for them as much as for the rep.

---

## 5. System architecture

```
Project 2: demo SPA (web/)              Project 1: console (console/)
  Vantage marketing page                  login · agent list · editor
  script src=".../embed.js?agent="        live dashboard · rep view · widget route
        │                                              │
        │ injects iframe                               │ console REST (cookie auth)
        ▼                                              ▼
┌──────────────── widget iframe: Agora Voice SDK ────────────────┐
└───────────────────────────┬────────────────────────────────────┘
                            │ RTC audio
        ┌───────────────────▼────────────────────────────────────┐
        │  Agora RTC channel (SD-RTN)                            │
        │  prospect · AI agent · (on escalation) human rep       │
        └───────────────────▲────────────────────────────────────┘
                            │ Agora Conversational AI Engine
                            │  ARES ASR · turn detection · interruption · TTS · filler words
                            │  payload generated from the agent record, never hand-written
                            │
                            │ OpenAI-compatible SSE (llm.vendor = "custom")
                            ▼
┌────────────────────── Backend: FastAPI ──────────────────────┐
│  /start-call · /stop-call     (agent lookup, token, join)    │
│  /v1/chat/completions         (LLM proxy, playbook, tools)   │
│  /console/*                   (login, agent CRUD)            │
│  /embed.js                    (loader script)                │
│  /events                      (dashboard stream)             │
│  tools layer, configured per agent                           │
└──────────────┬─────────────────────┬─────────────────────────┘
               │                     │
         Postgres                Groq · HubSpot · Cal.com · Slack
     agents · calls              (credentials per agent, from the DB)
```

**Split of ownership**

| Layer | Owner |
|---|---|
| Console app: login, agent list, editor, live dashboard, rep view, widget route | Keshav |
| Demo SPA: Vantage pages, embed integration | Keshav |
| FastAPI service, data model, agent lifecycle, LLM proxy, playbook, lead state, tools, integrations, embed loader | Aditi |
| The contracts in §6, acceptance rehearsal | Both |

---

## 6. Interface contracts

Frozen on day one. Everything else can change without coordination.

### 6.1 `POST /start-call`

Called by the widget when the prospect clicks Talk to Sales.

```jsonc
// request
{ "agent_id": "ag_8f2a", "prospect_name": "optional string", "page_context": "pricing" }

// response
{
  "app_id": "…",
  "channel": "pitchpilot-8f2a",
  "rtc_token": "007…",          // RTC + RTM privileges in one token
  "uid": "1002",
  "session_id": "sess_8f2a",
  "engine_agent_id": "1NT29X10YH…",   // from the engine's join response
  "agent_rtc_uid": "1001"
}
```

Backend work behind this endpoint:

1. Load the agent record. Unknown id gives 404.
2. **Validate the Origin header against the agent's allowed origins.** Agent ids are public — they sit in the embed snippet — so this check is what stops a stranger burning your Agora minutes. Reject with 403.
3. Generate a token carrying **both RTC and RTM privileges** — the agent reuses the same token for the RTM channel, so an RTC-only token breaks `enable_rtm`.
4. Build the engine payload from the agent's config (§12) and POST it to the engine's join endpoint.
5. Insert a `calls` row and return the engine's agent id for `/stop-call`.

`POST /stop-call` takes `{ "session_id": "…" }`, calls the engine's leave endpoint with the stored engine agent id, and writes the final lead state and outcome to the `calls` row. Call it explicitly — do not rely on `idle_timeout`.

### 6.2 Event stream

**Transcripts do not go through this schema.** The engine delivers live transcripts to the client itself over the configured data channel, and the client toolkit renders them. The console subscribes to those directly; the backend never republishes them. Our events carry only what the engine cannot know: the lead state and the outcomes.

`GET /events?agent_id=ag_8f2a` is a server-sent-events stream. Every message:

```jsonc
{ "type": "…", "session_id": "sess_8f2a", "ts": 1735689600000, "data": { } }
```

| `type` | `data` |
|---|---|
| `lead_state` | full lead-state object (§7), sent on every change |
| `tool_call` | `{ "name": "get_pricing", "args": { }, "result_summary": "Enterprise, 200 seats" }` |
| `outcome` | `{ "kind": "meeting_booked" \| "lead_qualified" \| "escalated", "detail": { } }` |
| `escalation` | `{ "reason": "…", "summary": "…", "channel": "pitchpilot-8f2a" }` |
| `call_ended` | `{ "duration_s": 214 }` |

The envelope is the contract; the transport is not. Everything publishes through one function in `backend/rtm.py`, so moving to the Agora RTM REST API later is a change to that function and to the console's subscriber.

### 6.3 `POST /v1/chat/completions` — the custom LLM

The engine speaks the OpenAI Chat Completions protocol. Hard requirements from the docs:

- **Streaming is mandatory.** The engine sends `stream: true`; a non-streaming reply is an error. Respond with SSE, one `data:` chunk at a time, ending with `data: [DONE]`.
- **Extra fields.** Because `llm.vendor` is `custom`, each message also carries `turn_id` (starts at 0, increments per turn) and `timestamp` (ms). Accept and ignore them, or log `turn_id` for debugging.
- **Identify the session.** The engine calls one fixed URL, so put the session in the URL configured at start time: `…/v1/chat/completions?session_id=sess_8f2a`. The proxy resolves session to call to agent, and loads that agent's config.

**Conversation history belongs to the engine.** It resends the window bounded by `max_history` on every turn. The proxy keeps only the lead state.

**Tool calls stay inside the proxy.** The proxy runs the tool loop and streams only final assistant text back. The engine never sees a tool-call delta.

**Non-interruptible turns** use a first-chunk metadata packet — an exact format, not a config flag:

```json
{ "id": "resp-1", "object": "chat.completion.custom_metadata",
  "choices": [], "metadata": { "interruptable": false } }
```

The engine reads only the **first** chunk for metadata and ignores its choices, so all spoken text must start in the second chunk. While non-interruptible, ASR keeps running and the prospect's speech is queued, not dropped. We use the engine's `greeting_message` for the AI disclosure instead, so nothing currently needs this.

### 6.4 Console API

All routes under `/console` require a valid session cookie. `POST /console/login` takes a password, compares it against `CONSOLE_PASSWORD` with a constant-time check, and sets a signed HttpOnly cookie.

| Route | Behaviour |
|---|---|
| `GET /console/agents` | id, name, updated_at, call count, last outcome |
| `POST /console/agents` | create from an AgentConfig; returns the new id |
| `GET /console/agents/{id}` | config and allowed origins. **Never returns secrets** |
| `PATCH /console/agents/{id}` | partial config update, validated against AgentConfig |
| `PATCH /console/agents/{id}/secrets` | write-only; reads back as `{"calcom_api_key": "set", "hubspot_token": null}` |
| `DELETE /console/agents/{id}` | cascades to calls |
| `GET /console/agents/{id}/calls` | call history with final lead state and outcome |

### 6.5 Embed

```html
<script src="https://api.example.com/embed.js?agent=ag_8f2a" async></script>
```

`GET /embed.js` returns a small loader that injects a launcher button and an iframe pointing at the console's widget route for that agent, carrying `allow="microphone"`.

An iframe rather than an inline widget: style isolation from the host page, no CSP negotiation, and the Agora SDK stays off the host's global scope. The cost is that microphone permission needs the host page on HTTPS with the allow attribute intact — verify on a genuinely third-party page early, not on demo day.

No Subresource Integrity hash on the snippet. The loader is first-party and meant to be redeployed; a pinned hash would break every existing embed on the next deploy. The allowed-origins check on `/start-call` is the control that matters on this surface.

---

## 7. Lead state

One per session, held in memory during the call, written to the `calls` row at the end.

```jsonc
{
  "session_id": "sess_8f2a",
  "company": null,
  "email": null,                  // CRM identity key; recorded when a meeting is booked
  "industry": null,
  "use_case": null,
  "seat_count": null,
  "budget_signal": null,          // "under_budget" | "stretch" | "over_budget" | null
  "timeline": null,               // "now" | "this_quarter" | "exploring" | null
  "objections_raised": [],        // ["pricing", "trust", "product"]
  "competitor_mentions": [],
  "bant": { "budget": 0, "authority": 0, "need": 0, "timeline": 0 },  // 0-3 each
  "qualification": "cold",        // derived, not model-set
  "next_action": null,            // "book_demo" | "send_followup" | "escalate"
  "notes": []
}
```

**Rules**

- Only `update_lead_state` writes to it. The model never edits it directly in text.
- Partial updates merge; arrays append without duplicates; a null never clears a set value.
- Every write publishes a `lead_state` event and updates the CRM contact (debounced: at most once every 10 s, plus once at call end). With no email there is no stable CRM identity, so the state is held in memory until one arrives.
- BANT scores are floored from what the call has established: `budget_signal` and
  `timeline` map to their scale, and a known seat count or use case scores need.
  The model may score higher, since it hears what the record does not, and that
  judgement is kept; the floor only ever raises a score. Authority has no recorded
  signal, so it stays the model's to set. Left to itself the model fills every other
  field and almost never scores BANT, which left demo-booking calls reading as cold.
- `qualification` is derived from the BANT sum: 9 or more is hot, 5 or more is warm, else cold.

---

## 8. Tools

Every tool reads its data and credentials from the agent record, not from process env or repo files.

| Tool | Signature | Behaviour |
|---|---|---|
| `get_pricing` | `(config, tier?, seats?)` | Tier, per-seat price, volume break, included features, from the agent's pricing table. |
| `get_battlecard` | `(config, competitor)` | Positioning, where we win, where we concede, one proof point. Unknown competitor returns an explicit no-data result the model must not paper over. |
| `update_lead_state` | `(**fields)` | Merges into lead state, returns the new state. |
| `check_slots` | `(secrets, days_ahead = 5)` | Cal.com availability, up to 5 human-readable slots. |
| `book_meeting` | `(secrets, slot_iso, email, name)` | Creates the Cal.com booking and the CRM deal. Idempotent per session. |
| `escalate_to_human` | `(secrets, reason)` | Summarises lead state, posts to Slack, publishes an escalation event, returns rep ETA text. |

**Tool discipline**

- Prices, availability and competitor claims come only from tools. If a tool has no data, the agent says so and offers to follow up — it never estimates.
- **Disabled tools are never offered.** The tool specs sent to the model are filtered by the agent's enabled-tools setting, so a disabled tool cannot be called rather than being refused after the fact.
- `book_meeting` requires an email; if missing, the tool returns an error the model handles conversationally.
- A tool that raises returns an error object as its tool result. A bad tool call is the model's problem to recover from, never a dead SSE stream.
- Every tool call publishes a `tool_call` event so the console shows the agent's work.

**Latency cover.** Tool calls stall the reply, so enable the engine's built-in filler words with a fixed-time trigger at ~1500 ms rather than writing our own waiting-message logic. It plays a short phrase while the proxy is still working, and it inherits the interruption setting.

**Alternative we are not taking.** The engine can call an MCP server directly, and Agora Studio ships a HubSpot connector. That would move our tools out of the proxy — but it also moves the lead-state logic out of our control, which is the part being judged. Keep tools in the proxy; mention the MCP path in the deck as an extension point.

---

## 9. The playbook

Not a script, and no longer a constant. The proxy assembles it per turn from the agent's config plus the live lead state.

**Operator-editable, from the console:**

1. **Identity.** Who the agent sells for, in one paragraph.
2. **Goal hierarchy.** Ordered. Default: book the demo, then qualify with BANT, then create a follow-up, then escalate.
3. **Objection strategies.** One free-text strategy per category — pricing, trust, product, competitor — seeded with the defaults below.
4. **Escalation triggers**, including a numeric deal-size threshold. Pick a number; do not leave it to the model.
5. **Greeting**, spoken by the engine and carrying the AI disclosure.

**Fixed, not editable.** These are the guarantees the product makes, so the console cannot weaken them:

- Never invent a price, feature, date or customer name; those come from tools.
- If a tool returns no data, say so; never estimate.
- Two or three sentences per turn. One question at a time.
- If interrupted, drop the previous point entirely; never resume it verbatim.
- Call `update_lead_state` on learning something, before replying.

**Seeded defaults** for a new agent. *Pricing*: reframe to per-seat value, probe the actual budget, offer a pilot, never discount unprompted. *Trust*: relevant case study, small pilot, or offer a human rep. *Product*: answer from tool data only; if the capability doesn't exist, say so plainly and pivot to what does. *Competitor*: call `get_battlecard` first, then acknowledge one genuine strength before positioning.

**Where the prompt lives.** The engine accepts `llm.system_messages` in the start payload, but our proxy assembles the prompt per turn (it has to inject the live lead state). Keep `system_messages` empty and treat the proxy as the single source of truth.

**Context management.** Groq's free tier caps tokens per minute. The engine's own `max_history` (default 32) bounds what it sends; the proxy trims further to the system prompt, the lead state, and the last 8 turns, collapsing older turns into a one-line summary.

---

## 10. Frontend

### 10.1 Console (Project 1)

**Login.** Single password against `CONSOLE_PASSWORD`, signed HttpOnly cookie. No user table, no registration.

**Agent list.** Name, last updated, call count, last outcome. Create and delete.

**Agent editor**, tabbed:

| Tab | Contents |
|---|---|
| Persona | Name, greeting, identity paragraph, goal hierarchy, the four objection strategies, escalation triggers and deal-size threshold |
| Voice | TTS vendor or managed preset, plus turn-detection and interruption tuning with the §12 values as defaults and a reset-to-default control |
| Knowledge | Pricing tier table editor (name, per-seat price, seat range, volume break, features) and battlecard editor (competitor, positioning, where we win, where we concede, proof point) |
| Integrations | Cal.com, HubSpot and Slack credentials plus the event-type id, and per-tool enable switches. Stored values show as "set", never as the value |
| Embed | The copyable script tag, the allowed-origins editor, and a note that an origin must be listed before a call will start |

**Live view** (`/agents/[id]/live`). Transcript from the engine's own stream, plus the lead-state panel fed by our events, with changed values briefly highlighted. Tool calls appear as inline chips.

**Rep view** (`/agents/[id]/escalations`). Incoming escalations with their summary and a Join Call button that joins the same RTC channel.

**Widget route** (`/widget?agent=…`). The call widget rendered chrome-free for the embed iframe: agent state ring (connecting, listening, thinking, speaking), mute, end call, elapsed timer. Mic permission before joining. Visible speaking indicator for both parties — this is how a viewer sees barge-in happen.

### 10.2 Demo SPA (Project 2)

Vantage: a fictional SaaS with a real-looking pricing table, generated from the demo agent's own pricing config so the page and the agent can never contradict each other. The Talk to Sales widget arrives via the embed script tag and nothing else — no bundled widget, no direct Agora SDK usage, no console code. If the embed breaks, this page shows it.

---

## 11. Non-functional requirements

| Area | Target |
|---|---|
| Turn latency | End of prospect speech to first agent audio under ~1.2 s |
| Barge-in | TTS stops within ~300 ms of detected speech |
| Config load | Agent config is read every turn; cache it for the life of a call so a cold database connection never sits in the tool path |
| Cost | Zero. Agora free tier, Groq free tier, HubSpot free CRM, Cal.com free plan, free-tier Postgres |
| Voice minutes | Conversational AI minutes are the scarce resource — text-mode testing for everything except integration runs |
| Failure behaviour | LLM timeout or tool error means the engine's failure message covers the spoken side; the proxy still logs the lead and creates a follow-up task |
| Secrets | Integration credentials are write-only across the API and never appear in a console read response, a log line, or an event payload |
| Privacy | Announce at call start that the call is AI-handled and transcribed. The engine's opt-out parameter disables Agora-side session retention if we want it |

---

## 12. Agora configuration reference

The console never shows this payload. The backend generates it from the agent record on every `/start-call`. Auth is HTTP Basic with base64 of the customer id and secret from the Agora console — platform-owned, one set, not per agent.

**Start:** POST to `https://api.agora.io/api/conversational-ai-agent/v2/projects/{appid}/join`
**Stop:** the matching leave endpoint with the engine agent id.
Also available and useful: interrupt (force-stop the agent from our backend), speak (make the agent say a fixed line over TTS — good for "connecting you to a colleague now"), think (inject an instruction mid-call), update, history, turns.

Fields marked **[cfg]** come from the agent record; everything else is fixed.

```jsonc
{
  "name": "pitchpilot-sess-8f2a",          // must be unique per agent instance
  "properties": {
    "channel": "pitchpilot-8f2a",
    "token": "<rtc+rtm token>",
    "agent_rtc_uid": "1001",
    "remote_rtc_uids": ["1002"],           // one uid only — the prospect
    "enable_string_uid": false,
    "idle_timeout": 60,

    "advanced_features": { "enable_rtm": true },

    "asr": { "vendor": "ares", "language": "en-US", "params": { } },

    "tts": { "vendor": "…", "params": { } },                    // [cfg] voice tab

    "llm": {
      "vendor": "custom",
      "url": "https://<public-url>/v1/chat/completions?session_id=sess_8f2a",
      "api_key": "<shared secret so the proxy can reject strangers>",
      "style": "openai",
      "system_messages": [],               // proxy owns the prompt
      "max_history": 32,
      "greeting_message": "…",             // [cfg] persona tab, carries the AI disclosure
      "failure_message": "Give me one moment.",
      "params": { "model": "openai/gpt-oss-20b", "stream": true }
    },

    "turn_detection": {                    // [cfg] voice tab, these values are the defaults
      "mode": "default",
      "config": {
        "speech_threshold": 0.5,
        "start_of_speech": {
          "mode": "vad",
          "vad_config": {
            "interrupt_duration_ms": 160,
            "speaking_interrupt_duration_ms": 320,
            "prefix_padding_ms": 800
          }
        },
        "end_of_speech": {
          "mode": "semantic",
          "semantic_config": {
            "silence_duration_ms": 320,
            "max_wait_ms": 3000,
            "pause_state_enabled": true
          }
        }
      }
    },

    "interruption": { "enable": true, "mode": "start_of_speech" },   // [cfg] voice tab

    "filler_words": {
      "enable": true,
      "trigger": { "mode": "fixed_time", "fixed_time_config": { "response_wait_ms": 1500 } },
      "content": {
        "mode": "static",
        "static_config": {
          "phrases": ["One moment.", "Let me check that.", "Pulling that up."],
          "selection_rule": "shuffle"
        }
      }
    },

    "parameters": {
      "data_channel": "rtm",
      "enable_metrics": true,
      "enable_error_message": true,
      "audio_scenario": "aiserver",
      "farewell_config": { "graceful_enabled": true, "graceful_timeout_seconds": 20 }
    }
  }
}
```

**Notes that will save hours**

- The turn-detection interrupt fields at the top level of `turn_detection` are **deprecated**. Since v2.6, turn detection handles start and end of speech only, and all interruption behaviour lives in the separate top-level `interruption` object. Most blog posts and tutorials still use the old shape.
- Semantic end-of-speech supports English and Chinese; other languages silently fall back to VAD.
- `speaking_interrupt_duration_ms` is the knob for over-eager barge-in — raise it if "mm-hmm" cuts the agent off, leaving `interrupt_duration_ms` low so the agent still starts listening quickly. This is the field the Voice tab exists for.
- `data_channel: "rtm"` only takes effect when `enable_rtm` is true, and metrics and error messages need it too.
- Presets with managed credential mode let Agora supply ASR and TTS credentials, so we may not need our own vendor keys at all. Try managed first; fall back to bring-your-own-key only if a preset we need isn't available.
- A Studio-published agent can supply the base config via pipeline id, with our properties overriding it. Not needed for us, but it is the migration path to Studio and SIP later.

---

## 13. Data model

Postgres, free tier. Access through asyncpg with no ORM and no migration tool: one `schema.sql` applied with create-if-not-exists on startup. Agent config is a single JSONB column, so adding a field to the builder never needs a migration.

```sql
agents(
  id              text primary key,       -- ag_8f2a
  name            text not null,
  config          jsonb not null,         -- AgentConfig: persona, voice, tuning, knowledge, tool toggles
  secrets         jsonb not null default '{}',   -- never selected by console reads
  allowed_origins text[] not null default '{}',
  created_at      timestamptz default now(),
  updated_at      timestamptz default now()
)

calls(
  session_id  text primary key,           -- sess_8f2a
  agent_id    text references agents(id) on delete cascade,
  started_at  timestamptz default now(),
  ended_at    timestamptz,
  duration_s  int,
  outcome     text,                       -- meeting_booked | lead_qualified | escalated | null
  lead_state  jsonb                       -- final snapshot, written on stop-call
)
```

`config` is validated by a Pydantic `AgentConfig` model shared by the console write path and the call runtime. That model is the interface between the two halves: the console cannot save a shape the runtime cannot read.

---

## 14. Build sequence

Every step ends with the acceptance scenario in §15 still passing in text mode.

**Phase 1 — data model.** Postgres schema, `AgentConfig`, database layer, and a seed that inserts today's Vantage pricing, battlecards and playbook as agent `ag_demo`. *Aditi.*

**Phase 2 — de-globalise the backend.** Every module-level constant becomes a per-agent argument: pricing and battlecard data, the playbook identity, the engine payload, the integration credentials. Tool specs get filtered by the enabled-tools setting. *Aditi. Gate: the acceptance scenario runs against `ag_demo` from the database and the 20 to 200 seat re-quote still fires.*

**Phase 3 — console skeleton.** Login, agent list, and the Persona and Knowledge tabs. *Keshav, against the §6.4 contract.*

**Phase 4 — embed.** The loader script, the widget route, and allowed-origin enforcement. *Both. Gate: a plain HTML file on a different origin, containing only the script tag, produces a working call.*

**Phase 5 — live surfaces.** Dashboard and rep view move into the console, scoped per agent. *Keshav.*

**Phase 6 — demo SPA.** Vantage rebuilt to consume the snippet and drop its bundled widget. *Keshav.*

**Phase 7 — remaining editor tabs.** Integrations with masked secrets, voice and turn-detection tuning, tool toggles. *Both.*

Voice runs are scheduled, not exploratory, at every phase.

---

## 15. Acceptance scenarios

### 15.1 The call

Run this verbatim; it is the evaluators' own example.

1. Prospect asks the price for about 20 users. → Agent quotes the mid tier from `get_pricing`.
2. Mid-answer, prospect interrupts: "how does that compare to \<Competitor\>?" → Agent stops immediately, calls `get_battlecard`, answers the comparison, does not resume the interrupted sentence.
3. "Actually it'd be closer to 200 users." → `update_lead_state(seat_count=200)`, next quote is the enterprise tier, unprompted.
4. "That's a lot more than we budgeted." → Pricing strategy fires: per-seat reframe, budget probe, pilot offer. No unprompted discount.
5. "Can we see an enterprise demo?" → `check_slots`, prospect picks one, `book_meeting` creates the Cal.com booking and the HubSpot deal, agent confirms aloud.
6. Dashboard shows lead state populated: company, 200 seats, one pricing objection, one competitor mention, BANT scored, `next_action: book_demo`.

Pass = all six, in one unbroken call, with no restart.

### 15.2 The build

New for the two-project split. Run it on a machine that has never seen the repo.

1. Log into the console, create an agent, fill in identity, greeting, two pricing tiers and one battlecard.
2. Add one allowed origin. Copy the embed snippet.
3. Paste the snippet into a plain HTML file served from that origin, and open it.
4. The launcher appears, the mic prompt appears, and the call connects to the agent just configured — its greeting, its prices.
5. Change the escalation threshold in the console. The next call uses the new value with no redeploy.
6. Serve the same file from an origin that is not on the list. The call is refused.

Pass = all six, without opening the Agora dashboard once.

---

## 16. Risks

| Risk | Mitigation |
|---|---|
| Conversational AI minutes run out mid-build | All brain work in text mode; voice runs are scheduled, not exploratory. Low idle timeout and explicit leave on hang-up so idle agents don't burn minutes |
| The split stalls the thing being judged | §15.1 is the pass bar and it must pass at the end of every phase. If the console slips, a seeded `ag_demo` still runs the full scenario |
| Groq free-tier token limits with long calls | Groq is the only provider, so there is no failover: aggressive history trimming is the whole mitigation. The proxy sends the system prompt, the lead state and the last 8 turns, collapsing older ones into one line. A turn that still gets rate-limited falls to the engine's `failure_message`, and the proxy logs the lead and sets a follow-up |
| Over-eager barge-in | Raise `speaking_interrupt_duration_ms` in the Voice tab; keep semantic end-of-speech on rather than raw VAD |
| Copying a deprecated config from a tutorial | §12 is the reference; anything setting interrupt fields inside `turn_detection` is out of date |
| The engine can't reach our proxy | Public tunnel required from day one — localhost will never work. Verify with a curl from outside the LAN before blaming the engine |
| Microphone blocked in the embed iframe | Needs HTTPS on the host page and an intact allow attribute. Test on a real third-party origin in Phase 4, not on demo day |
| Integration secrets leak through the console API | Secrets are write-only, masked on read, excluded from logs and events. One shared operator password gates every console route |
| Free-tier Postgres cold starts land in the tool path | Cache each agent's config for the life of a call; it changes only from the console |
| Config drift between the model and the frontends | One Pydantic `AgentConfig` is the source of truth; the frontends mirror it in one direction only |
| Tool latency stacking on LLM latency | Local structured data for pricing and battlecards; CRM writes fire-and-forget after the reply is sent; filler words cover the gap audibly |
| Model invents a price despite the playbook | Prices only enter context as tool results; spot-check transcripts during testing |
| Cal.com or HubSpot friction late in the build | Both behind an interface with a local stub, so a failed integration degrades to a logged outcome instead of a broken call |

---

## 17. Environment

Platform-level only. Per-agent integration credentials live in the database, not here.

```
AGORA_APP_ID=            AGORA_APP_CERTIFICATE=     # token generation
AGORA_CUSTOMER_ID=       AGORA_CUSTOMER_SECRET=     # Basic auth for the engine REST API
GROQ_API_KEY=                                       # the only LLM provider
TTS_VENDOR_KEY=                                     # only if managed mode is not used
LLM_PROXY_SECRET=                                   # matches properties.llm.api_key
DATABASE_URL=                                       # Postgres, free tier
CONSOLE_PASSWORD=                                   # single operator login
CONSOLE_SESSION_SECRET=                             # signs the console cookie
CONSOLE_URL=                                        # where the embed iframe points
PUBLIC_BASE_URL=                                    # tunnel; the engine calls this
```

---

## 18. Repo layout

```
pitchpilot/
├── backend/
│   ├── main.py            # FastAPI app, /start-call, /stop-call, /events, /embed.js
│   ├── console.py         # login + agent CRUD, mounted at /console
│   ├── proxy.py           # /v1/chat/completions, SSE, tool loop
│   ├── models.py          # AgentConfig, AgentSecrets, LeadState
│   ├── db.py              # asyncpg pool, agent and call queries
│   ├── schema.sql         # agents, calls
│   ├── seed.py            # inserts ag_demo from the Vantage data
│   ├── playbook.py        # prompt assembly from config
│   ├── state.py           # lead state store + BANT scoring
│   ├── tools/             # pricing, battlecards, crm, calendar, escalation
│   ├── rtm.py             # event publisher
│   ├── agora.py           # engine payload builder + join/leave/speak
│   ├── token2.py          # AccessToken2 with RTC + RTM privileges
│   └── data/              # seed pricing.json, battlecards.json
├── console/               # Project 1 — Next.js
│   ├── app/login/
│   ├── app/agents/            # list
│   ├── app/agents/[id]/       # editor tabs
│   ├── app/agents/[id]/live/  # dashboard
│   ├── app/agents/[id]/escalations/
│   ├── app/widget/            # chrome-free widget for the embed iframe
│   └── lib/                   # api client, types mirrored from models.py
├── web/                   # Project 2 — Next.js, the Vantage demo
│   ├── app/page.tsx           # pricing page + embed script tag
│   └── lib/
└── README.md
```

---

## 19. Open questions

1. **Managed mode or our own keys?** Try a managed preset for ASR and TTS first; it removes the vendor-signup question entirely. Decide in Phase 1, since it sits in the start payload and therefore in the Voice tab.
2. Does the rep view need its own token endpoint, or can it reuse `/start-call` with a rep role flag?
3. Should `escalate_to_human` use the engine's speak endpoint for the hand-off line, so it is guaranteed to play even if the LLM is mid-thought?
4. Does the Knowledge tab need CSV import for pricing tiers, or is a hand-edited table enough for the demo?
5. Should a brand-new agent be created from a template with the seeded defaults already filled in, or from an empty form? A template makes §15.2 much faster to run.
6. Is one shared operator password enough for the judges' environment, or does the console need to be behind a tunnel that is never published?
