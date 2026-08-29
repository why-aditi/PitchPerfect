# PitchPilot — Product Requirements Document

**Team:** Hecker (Aditi Kala, Keshav Sharma)
**Track:** Adaptive AI Sales and Negotiation Agent — EchoSphere 2026
**Status:** Draft for build round
**Owner of this doc:** Aditi

> Agora API details in this document were verified against `docs.agora.io` (Conversational AI Engine REST reference and the custom-LLM guide) on 29 Aug 2026. Where a field is deprecated, the current replacement is used and the old name is noted.

---

## 1. Summary

PitchPilot is a real-time voice AI sales agent that lives as a "Talk to Sales" widget on a product website. A prospect clicks it, speaks to the agent in the browser, and can interrupt, compare competitors, object on price, and change requirements mid-call. The agent qualifies them, answers from real pricing and battlecard data, and drives the call to a concrete outcome: a booked demo, a qualified lead in the CRM, or a warm hand-off to a human rep who joins the same live call.

There is no call script anywhere in the system. The agent reasons every turn over a structured lead-state object it maintains through tool calls, plus a sales playbook in the system prompt.

## 2. Goals

| # | Goal | How we know it's met |
|---|---|---|
| G1 | Natural turn-taking with true barge-in | Agent stops speaking within ~300 ms of the prospect starting, and its next reply reflects what was said, not what it was about to say |
| G2 | Session memory that propagates | A mid-call change from 20 to 200 seats changes the very next quote, with no restart and no re-asking |
| G3 | Grounded answers | Every price, feature and calendar slot in a transcript traces to a tool call, not model memory |
| G4 | Adaptive objection handling | Pricing, trust and product objections each get a distinct strategy, chosen at runtime |
| G5 | Concrete outcome per call | Call ends with a booking, a qualified CRM record, or an escalation, never a dead end |
| G6 | Escalation with context | Human rep joins the same channel and has a written summary before they speak |

## 3. Non-goals

- **Outbound / PSTN calling.** Browser-to-agent only. SIP telephony via Conversational AI Studio is post-hackathon.
- **Multi-tenant SaaS.** One demo product catalogue, one agent persona.
- **Model training or fine-tuning.** All hosted APIs, no GPU.
- **RAG over long documents.** Product data is a small structured store exposed as tools. Stretch goal only.
- **Authentication / accounts.** No prospect login.
- **Mobile-native app.** Responsive web is enough.

## 4. Users

**Prospect (primary).** On the pricing page, has a question, does not want a form or a callback in three days. Wants an answer now and will interrupt if the agent rambles.

**Sales rep (secondary).** Watches the dashboard, gets pulled into calls that need a human. Wants context before speaking, not after.

**Evaluator (tertiary).** Needs to see the adaptive behaviour actually happen — the visible lead state is for them as much as for the rep.

---

## 5. System architecture

```
Browser (prospect)                         Browser (rep dashboard)
  Agora Voice SDK for Web                    Agora RTM client + Voice SDK
        │                                              │
        │ RTC audio        transcripts (engine → client via RTM/datastream)
        │                  lead_state + outcomes (our backend → RTM)
        ▼                                              ▼
┌───────────────────────────── Agora RTC channel (SD-RTN) ─────────────────────────────┐
│  participants: prospect · AI agent · (on escalation) human rep                        │
└───────────────────────────────────────────────────────────────────────────────────────┘
        ▲
        │ Agora Conversational AI Engine
        │   ARES ASR · turn detection (VAD SoS + semantic EoS) · interruption · TTS · filler words
        │
        │ OpenAI-compatible SSE (llm.vendor = "custom")
        ▼
┌────────────────────── Backend: FastAPI ──────────────────────┐
│  /start-call · /stop-call        (token + agent lifecycle)   │
│  /v1/chat/completions            (LLM proxy: playbook,       │
│                                   lead state, tool calls)    │
│  tools layer                                                 │
│    get_pricing · get_battlecard · update_lead_state          │
│    check_slots · book_meeting · escalate_to_human            │
│  RTM publisher (lead_state, tool_call, outcome, escalation)  │
└──────────────┬──────────────────────┬────────────────────────┘
               │                      │
        Groq / Gemini          HubSpot · Cal.com · pricing & battlecard store
```

**Split of ownership**

| Layer | Owner |
|---|---|
| Marketing page, call widget, dashboard, rep view, all browser SDK code | Keshav |
| FastAPI service, agent lifecycle, LLM proxy, playbook, lead state, tools, integrations | Aditi |
| The three contracts in §6, acceptance scenario rehearsal | Both |

---

## 6. Interface contracts

These three are frozen on day one. Everything else can change without coordination.

### 6.1 `POST /start-call`

Called by the widget when the prospect clicks Talk to Sales.

```jsonc
// request
{ "prospect_name": "optional string", "page_context": "pricing" }

// response
{
  "app_id": "…",
  "channel": "pitchpilot-8f2a",
  "rtc_token": "007…",          // RTC + RTM privileges in one token
  "uid": "1002",
  "session_id": "sess_8f2a",
  "agent_id": "1NT29X10YH…",    // from the engine's join response
  "agent_rtc_uid": "1001"
}
```

Backend work behind this endpoint:

1. Generate a token carrying **both RTC and RTM privileges** — the agent reuses the same token for the RTM channel, so an RTC-only token breaks `enable_rtm`.
2. `POST https://api.agora.io/api/conversational-ai-agent/v2/projects/{appid}/join` with the payload in §12.
3. Return `agent_id` and store it against `session_id` for `/stop-call`.

`POST /stop-call` takes `{ "session_id": "…" }` and calls the engine's `leave` endpoint with the stored `agent_id`. Call it explicitly — do not rely on `idle_timeout`.

### 6.2 RTM message schema

**Transcripts do not go through this schema.** The engine delivers live transcripts to the client itself over the configured data channel, and the client toolkit renders them. Keshav subscribes to those directly; the backend never republishes them. Our RTM messages carry only what the engine cannot know: the lead state and the outcomes.

Backend publishes to channel `pitchpilot-<id>-events`. Every message:

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

Keshav can build the whole dashboard against a mock publisher emitting these before the brain exists.

### 6.3 `POST /v1/chat/completions` — the custom LLM

The engine speaks the OpenAI Chat Completions protocol. Hard requirements from the docs:

- **Streaming is mandatory.** The engine sends `stream: true`; a non-streaming reply is an error. Respond with SSE, `data: {chunk}\n\n` per chunk, ending `data: [DONE]\n\n`.
- **Extra fields.** Because `llm.vendor` is `custom`, each message also carries `turn_id` (starts at 0, increments per turn) and `timestamp` (ms). Accept and ignore them, or log `turn_id` for debugging.
- **Identify the session.** The engine calls one fixed URL, so put the session in the URL configured at start time: `…/v1/chat/completions?session_id=sess_8f2a`.

**Tool calls stay inside the proxy.** The proxy runs the tool loop against Groq and streams only final assistant text back. The engine never sees a `tool_calls` delta.

**Non-interruptible turns** use a first-chunk metadata packet — this is an exact format, not a config flag:

```json
{ "id": "resp-1", "object": "chat.completion.custom_metadata",
  "choices": [], "metadata": { "interruptable": false } }
```

The engine reads only the **first** chunk for metadata and ignores its `choices`, so all spoken text must start in the second chunk. While non-interruptible, ASR keeps running and the prospect's speech is queued, not dropped — it gets processed once playback ends. Use this for the AI disclosure line and nothing else; over-using it makes the agent feel deaf.

The same mechanism can swap TTS parameters mid-call via `metadata.tts_params.params` — out of scope, noted for the roadmap.

---

## 7. Lead state

The core object. One per session, held in memory (dict keyed by `session_id`), mirrored to RTM on every write.

```jsonc
{
  "session_id": "sess_8f2a",
  "company": null,
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
- Partial updates merge; arrays append without duplicates.
- Every write publishes a `lead_state` RTM message and updates the HubSpot contact (debounced: at most once every 10 s, plus once at call end).
- `qualification` is derived from the BANT sum: ≥9 hot, ≥5 warm, else cold.

---

## 8. Tools

| Tool | Signature | Behaviour |
|---|---|---|
| `get_pricing` | `(tier?: str, seats?: int)` | Tier, per-seat price, volume break, included features. Enterprise threshold at ≥100 seats. Reads `data/pricing.json`. |
| `get_battlecard` | `(competitor: str)` | Positioning, where we win, where we concede, one proof point. Unknown competitor returns an explicit "no data" the model must not paper over. |
| `update_lead_state` | `(**fields)` | Merges into lead state, returns the new state. |
| `check_slots` | `(days_ahead: int = 5)` | Cal.com availability, up to 5 human-readable slots. |
| `book_meeting` | `(slot_iso, email, name)` | Creates the Cal.com booking and the HubSpot deal. Idempotent per session. |
| `escalate_to_human` | `(reason: str)` | Summarises lead state + transcript, posts to Slack, publishes `escalation` over RTM, returns rep ETA text. |

**Tool discipline**

- Prices, availability and competitor claims come only from tools. If a tool has no data, the agent says so and offers to follow up — it never estimates.
- `book_meeting` requires an email; if missing, the tool returns an error the model handles conversationally.
- Every tool call publishes a `tool_call` RTM message so the dashboard shows the agent's work.

**Latency cover.** Tool calls stall the reply, so enable the engine's built-in `filler_words` with `trigger.mode = "fixed_time"` at ~1500 ms rather than writing our own waiting-message logic. It plays a short phrase while the proxy is still working, and it inherits the interruption setting.

**Alternative we are not taking.** The engine can call an MCP server directly (`advanced_features.enable_tools` + `llm.mcp_servers`), and Agora Studio ships a HubSpot connector. That would move our tools out of the proxy — but it also moves the lead-state logic out of our control, which is the part being judged. Keep tools in the proxy; mention the MCP path in the deck as an extension point.

---

## 9. The playbook (system prompt design)

Not a script. Sections in this order:

1. **Identity and constraint.** Who the agent sells for, and: never invent a price, feature, date or customer name.
2. **Current lead state**, injected as JSON on every turn.
3. **Goal hierarchy.** Book the demo > qualify with BANT > create a follow-up > escalate. Pursue the highest goal the conversation supports; never force it.
4. **Objection strategies.**
   - *Pricing* → reframe to per-seat value, probe the actual budget, offer a pilot. Never discount unprompted.
   - *Trust* → relevant case study, small pilot, or offer a human rep.
   - *Product* → answer from tool data only; if the capability doesn't exist, say so plainly and pivot to what does.
   - *Competitor* → `get_battlecard` first, then acknowledge one genuine strength before positioning.
5. **Conversational rules.** Two or three sentences per turn — the prospect is listening, not reading. One question at a time. If interrupted, drop the previous point entirely; never resume it verbatim.
6. **When to escalate.** Explicit request, legal or security questions, repeated frustration, or deal size above a fixed threshold.

**Where the prompt lives.** The engine accepts `llm.system_messages` in the start payload, but our proxy assembles the prompt per turn (it has to inject the live lead state). Keep `system_messages` minimal or empty and treat the proxy as the single source of truth, so there is only one place to edit.

**Context management.** Groq's free tier caps tokens per minute. The engine's own `max_history` (default 32) bounds what it sends; the proxy trims further to the system prompt, the lead state, and the last 8 turns, collapsing older turns into a one-line summary.

---

## 10. Frontend

**Landing page.** A fake SaaS product with a real-looking pricing table (generated from the same `pricing.json` the agent reads, so page and agent can never contradict each other) and a persistent "Talk to Sales" button.

**Call widget.** Dialer-style panel: agent state ring (connecting → listening → thinking → speaking), mute, end call, elapsed timer. Mic permission before joining. Visible speaking indicator for both parties — this is how a viewer sees barge-in happen.

**Dashboard pane.** Live transcript from the engine's own transcript stream, plus the lead-state panel fed by our RTM events, with changed values briefly highlighted. Tool calls appear as inline chips.

**Rep view.** Separate route. Lists incoming escalations with their summary and a Join Call button that joins the same RTC channel.

---

## 11. Non-functional requirements

| Area | Target |
|---|---|
| Turn latency | End of prospect speech → first agent audio under ~1.2 s |
| Barge-in | TTS stops within ~300 ms of detected speech |
| Cost | Zero. Agora free tier, Groq/Gemini free tiers, HubSpot free CRM, Cal.com free plan |
| Voice minutes | Conversational AI minutes are the scarce resource — text-mode testing for everything except integration runs |
| Failure behaviour | LLM timeout or tool error → `llm.failure_message` covers the spoken side; the proxy still logs the lead and creates a follow-up task |
| Privacy | Announce at call start that the call is AI-handled and transcribed. `parameters.opt_out` disables Agora-side session retention if we want it |

---

## 12. Agora configuration reference

Verified against the current REST reference. Auth is HTTP Basic with base64(`customer_id:customer_secret`) from the Agora console.

**Start:** `POST https://api.agora.io/api/conversational-ai-agent/v2/projects/{appid}/join`
**Stop:** the matching `leave` endpoint with `agent_id`.
Also available and useful: `interrupt` (force-stop the agent from our backend), `speak` (make the agent say a fixed line over TTS — good for "connecting you to a colleague now"), `think` (inject an instruction mid-call), `update`, `history`, `turns`.

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

    "tts": { "vendor": "…", "params": { } },

    "llm": {
      "vendor": "custom",
      "url": "https://<public-url>/v1/chat/completions?session_id=sess_8f2a",
      "api_key": "<shared secret so the proxy can reject strangers>",
      "style": "openai",
      "system_messages": [],               // proxy owns the prompt
      "max_history": 32,
      "greeting_message": "Hi, you're speaking with an AI sales assistant …",
      "failure_message": "Give me one moment.",
      "params": { "model": "llama-3.3-70b-versatile", "stream": true }
    },

    "turn_detection": {
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

    "interruption": { "enable": true, "mode": "start_of_speech" },

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

- `turn_detection.interrupt_mode`, `interrupt_duration_ms`, `threshold` and friends at the top level of `turn_detection` are **deprecated**. Since v2.6, turn detection handles start/end of speech only, and all interruption behaviour lives in the separate top-level `interruption` object. Most blog posts and tutorials still use the old shape.
- Semantic end-of-speech supports English and Chinese; other languages silently fall back to VAD.
- `speaking_interrupt_duration_ms` is the knob for over-eager barge-in — raise it if "mm-hmm" cuts the agent off, leaving `interrupt_duration_ms` low so the agent still starts listening quickly.
- `data_channel: "rtm"` only takes effect when `advanced_features.enable_rtm` is true, and `enable_metrics` / `enable_error_message` need it too.
- Presets with `credential_mode: "managed"` let Agora supply ASR/TTS credentials, so we may not need our own vendor keys at all. Try managed first; fall back to bring-your-own-key only if a preset we need isn't available.
- `pipeline_id` lets a Studio-published agent supply the base config, with `properties` overriding it. Not needed for us, but it is the migration path to Studio and SIP later.

---

## 13. Build sequence

**Phase 1 — talking agent.** Token endpoint (RTC + RTM privileges), join/leave calls, browser joins channel, minimal prompt, agent answers and can be interrupted. *Both. Gate: a human can interrupt it and it recovers.*

**Phase 2 — the brain.** LLM proxy with playbook, lead state, `update_lead_state`, `get_pricing`, `get_battlecard` against local JSON. Tested entirely in text via curl against the SSE endpoint. *Aditi. Gate: the 20 → 200 seat change re-quotes correctly in a text transcript.*

**Phase 3 — outcomes.** Cal.com and HubSpot integration, `check_slots`, `book_meeting`, escalation summary + Slack. *Aditi.*

**Phase 4 — surfaces.** Landing page, call widget, transcript rendering, lead-state dashboard, rep view. *Keshav, in parallel from Phase 1 using a mock RTM publisher.*

**Phase 5 — integration.** Point the engine at the tunnelled proxy, tune `speaking_interrupt_duration_ms` and the semantic EoS timings, run the acceptance scenario end to end.

---

## 14. Acceptance scenario

Run this verbatim; it is the evaluators' own example.

1. Prospect asks the price for about 20 users. → Agent quotes the mid tier from `get_pricing`.
2. Mid-answer, prospect interrupts: "how does that compare to \<Competitor\>?" → Agent stops immediately, calls `get_battlecard`, answers the comparison, does not resume the interrupted sentence.
3. "Actually it'd be closer to 200 users." → `update_lead_state(seat_count=200)`, next quote is the enterprise tier, unprompted.
4. "That's a lot more than we budgeted." → Pricing strategy fires: per-seat reframe, budget probe, pilot offer. No unprompted discount.
5. "Can we see an enterprise demo?" → `check_slots`, prospect picks one, `book_meeting` creates the Cal.com booking and the HubSpot deal, agent confirms aloud.
6. Dashboard shows lead state populated: company, 200 seats, one pricing objection, one competitor mention, BANT scored, `next_action: book_demo`.

Pass = all six, in one unbroken call, with no restart.

---

## 15. Risks

| Risk | Mitigation |
|---|---|
| Conversational AI minutes run out mid-build | All brain work in text mode; voice runs are scheduled, not exploratory. `idle_timeout` low and explicit `leave` on hang-up so idle agents don't burn minutes |
| Groq free-tier token limits with long calls | Aggressive history trimming; Gemini Flash key configured as fallback |
| Over-eager barge-in | Raise `speaking_interrupt_duration_ms`; keep semantic EoS on rather than raw VAD |
| Copying a deprecated config from a tutorial | §12 is the reference; anything using `turn_detection.interrupt_mode` is out of date |
| The engine can't reach our proxy | Public tunnel required from day one — localhost will never work. Verify with a curl from outside the LAN before blaming the engine |
| Tool latency stacking on LLM latency | Local JSON for pricing/battlecards; CRM writes fire-and-forget after the reply is sent; `filler_words` covers the gap audibly |
| Model invents a price despite the playbook | Prices only enter context as tool results; spot-check transcripts during testing |
| HubSpot/Cal.com API friction late in the build | Both behind an interface with a local stub, so a failed integration degrades to a logged outcome instead of a broken call |

---

## 16. Environment

```
AGORA_APP_ID=            AGORA_APP_CERTIFICATE=     # token generation
AGORA_CUSTOMER_ID=       AGORA_CUSTOMER_SECRET=     # Basic auth for the engine REST API
GROQ_API_KEY=            GEMINI_API_KEY=            # fallback
TTS_VENDOR_KEY=                                     # only if managed mode is not used
LLM_PROXY_SECRET=                                   # matches properties.llm.api_key
HUBSPOT_TOKEN=           CALCOM_API_KEY=
SLACK_WEBHOOK_URL=
PUBLIC_BASE_URL=                                    # tunnel; the engine calls this
```

## 17. Repo layout

```
pitchpilot/
├── backend/
│   ├── main.py            # FastAPI app, /start-call, /stop-call
│   ├── proxy.py           # /v1/chat/completions, SSE, tool loop, metadata first-chunk
│   ├── playbook.py        # system prompt assembly
│   ├── state.py           # lead state store + BANT scoring
│   ├── tools/             # pricing, battlecards, crm, calendar, escalation
│   ├── rtm.py             # event publisher
│   ├── agora.py           # token generation + join/leave/interrupt/speak clients
│   └── data/              # pricing.json, battlecards.json
├── web/
│   ├── index.html         # landing + pricing + Talk to Sales
│   ├── call.js            # Agora Voice SDK, widget state machine, transcripts
│   ├── dashboard.js       # RTM subscriber, lead state
│   └── rep.html           # escalation view
└── README.md
```

---

## 18. Open questions

1. **Managed mode or our own keys?** Try a managed preset for ASR/TTS first; it removes the vendor-signup question entirely. Decide in Phase 1, since it sits in the start payload.
2. Does the rep view need its own token endpoint, or can it reuse `/start-call` with a `role=rep` flag?
3. AI disclosure: use `llm.greeting_message` (spoken, engine-owned) or a non-interruptible first turn from the proxy? Greeting is simpler and `greeting_configs.interruptable: false` already exists.
4. Escalation threshold on deal size — pick a number and put it in the playbook, don't leave it to the model.
5. Should `escalate_to_human` use the engine's `speak` endpoint for the hand-off line, so it is guaranteed to play even if the LLM is mid-thought?