// Mirrored by hand from backend/models.py. One direction only: models.py is the source
// of truth, this file follows it. Drift here is the likeliest bug in the whole split.

export type Tier = {
  name: string;
  per_seat_month: number;
  min_seats: number;
  max_seats: number | null;
  volume_break: { seats: number; per_seat_month: number } | null;
  features: string[];
};

export type Battlecard = {
  positioning: string;
  we_win: string[];
  we_concede: string[];
  proof_point: string;
};

/** One rung of the ladder. `require` is what has to come back; a rung without one is a
 *  discount with extra steps, which is the thing this whole mechanism exists to prevent. */
export type Concession = {
  give: string;
  require: string;
  min_seats: number;
};

export type Knowledge = {
  currency: string;
  tiers: Tier[];
  battlecards: Record<string, Battlecard>;
  /** Ordered, cheapest first. The order is the offering order. */
  concessions: Concession[];
};

export type Persona = {
  identity: string;
  greeting: string;
  goal_hierarchy: string[];
  objection_strategies: Record<"pricing" | "trust" | "product" | "competitor", string>;
  escalation_triggers: string[];
  escalation_seat_threshold: number;
};

export type Voice = {
  tts_vendor: string;
  tts_params: Record<string, unknown>;
  speech_threshold: number;
  interrupt_duration_ms: number;
  speaking_interrupt_duration_ms: number;
  prefix_padding_ms: number;
  silence_duration_ms: number;
  max_wait_ms: number;
  interruption_enabled: boolean;
  filler_phrases: string[];
};

export type ToolsEnabled = {
  pricing: boolean;
  battlecards: boolean;
  calendar: boolean;
  crm: boolean;
  escalation: boolean;
  negotiation: boolean;
};

export type AgentConfig = {
  persona: Persona;
  voice: Voice;
  knowledge: Knowledge;
  tools_enabled: ToolsEnabled;
  llm_model: string;
};

/** Secrets only ever arrive masked: "set" or null. */
export type SecretsSet = {
  calcom_api_key: "set" | null;
  calcom_event_type_id: string | null;
  hubspot_token: "set" | null;
  hubspot_pipeline: string;
  hubspot_deal_stage: string;
  slack_webhook_url: "set" | null;
  notion_token: "set" | null;
  notion_leads_db: string | null;
};

export type Agent = {
  id: string;
  name: string;
  config: AgentConfig;
  allowed_origins: string[];
  secrets_set: SecretsSet;
};

export type AgentSummary = {
  id: string;
  name: string;
  updated_at: string;
  call_count: number;
  last_outcome_at: string | null;
};

export type LeadState = {
  session_id: string;
  company: string | null;
  email: string | null;
  industry: string | null;
  use_case: string | null;
  seat_count: number | null;
  budget_signal: "under_budget" | "stretch" | "over_budget" | null;
  timeline: "now" | "this_quarter" | "exploring" | null;
  objections_raised: string[];
  competitor_mentions: string[];
  /** What this call actually committed to, in the order it was given. Written by the
   *  dispatcher from propose_concession results, never by the model. */
  concessions_offered: string[];
  bant: { budget: number; authority: number; need: number; timeline: number };
  qualification: "cold" | "warm" | "hot";
  next_action: "book_demo" | "send_followup" | "escalate" | null;
  notes: string[];
};

export type Session = {
  app_id: string;
  channel: string;
  rtc_token: string;
  uid: string;
  session_id: string;
  engine_agent_id: string;
  agent_rtc_uid: string;
};

// PRD 6.2 — every event has this envelope.
export type RtmEvent =
  | { type: "lead_state"; session_id: string; ts: number; data: LeadState }
  | { type: "tool_call"; session_id: string; ts: number; data: { name: string; args: Record<string, unknown>; result_summary: string } }
  | { type: "outcome"; session_id: string; ts: number; data: { kind: "meeting_booked" | "lead_qualified" | "escalated"; detail: Record<string, unknown> } }
  | { type: "escalation"; session_id: string; ts: number; data: { reason: string; summary: string; channel: string } }
  | { type: "call_ended"; session_id: string; ts: number; data: { duration_s: number } };

export type CallState = "idle" | "connecting" | "listening" | "thinking" | "speaking";

export type CallRecord = {
  session_id: string;
  started_at: string;
  ended_at: string | null;
  duration_s: number | null;
  outcome: string | null;
  lead_state: LeadState | null;
};

/** Derived, not sent: sess_8f2a -> pitchpilot-8f2a, minted from the same suffix in main.py. */
export const channelFor = (sessionId: string) =>
  `pitchpilot-${sessionId.replace(/^sess_/, "")}`;
