export type Tier = {
  name: string;
  per_seat_month: number;
  min_seats: number;
  max_seats: number | null;
  volume_break: { seats: number; per_seat_month: number } | null;
  features: string[];
};

export type Pricing = { currency: string; enterprise_seat_threshold: number; tiers: Tier[] };

export type LeadState = {
  session_id: string;
  company: string | null;
  industry: string | null;
  use_case: string | null;
  seat_count: number | null;
  budget_signal: "under_budget" | "stretch" | "over_budget" | null;
  timeline: "now" | "this_quarter" | "exploring" | null;
  objections_raised: string[];
  competitor_mentions: string[];
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
  agent_id: string;
  agent_rtc_uid: string;
};

// PRD 6.2 — every RTM message has this envelope.
export type RtmEvent =
  | { type: "lead_state"; session_id: string; ts: number; data: LeadState }
  | { type: "tool_call"; session_id: string; ts: number; data: { name: string; args: Record<string, unknown>; result_summary: string } }
  | { type: "outcome"; session_id: string; ts: number; data: { kind: "meeting_booked" | "lead_qualified" | "escalated"; detail: Record<string, unknown> } }
  | { type: "escalation"; session_id: string; ts: number; data: { reason: string; summary: string; channel: string } }
  | { type: "call_ended"; session_id: string; ts: number; data: { duration_s: number } };

export type CallState = "idle" | "connecting" | "listening" | "thinking" | "speaking";
