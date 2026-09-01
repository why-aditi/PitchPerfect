import type { TranscriptLine } from "@/lib/transcript";
import type { LeadState, RtmEvent } from "@/lib/types";

/**
 * The §15.1 acceptance call, as a timed sequence of the events the backend would publish.
 *
 * It exists so the live view is demonstrable and testable with no backend, no Agora
 * minutes and no microphone: the runner pushes each event through window.emit, so it
 * travels the same subscriber path a real call does. The transcript half is scripted
 * rather than decoded, which is why the screen labels a replay as a replay — the one
 * thing worse than an undemoable dashboard is one showing invented data as live.
 */

export const DEMO_SESSION = "sess_replay";

export type Step = { at: number; event?: RtmEvent; line?: TranscriptLine };

const BASE: LeadState = {
  session_id: DEMO_SESSION,
  company: null,
  email: null,
  industry: null,
  use_case: null,
  seat_count: null,
  budget_signal: null,
  timeline: null,
  objections_raised: [],
  competitor_mentions: [],
  bant: { budget: 0, authority: 0, need: 0, timeline: 0 },
  qualification: "cold",
  next_action: null,
  notes: [],
};

export function demoScript(now: number): Step[] {
  const lead = (at: number, patch: Partial<LeadState>): Step => ({
    at,
    event: { type: "lead_state", session_id: DEMO_SESSION, ts: now + at, data: { ...BASE, ...patch } },
  });
  const tool = (at: number, name: string, result_summary: string): Step => ({
    at,
    event: {
      type: "tool_call",
      session_id: DEMO_SESSION,
      ts: now + at,
      data: { name, args: {}, result_summary },
    },
  });
  const say = (
    at: number,
    role: TranscriptLine["role"],
    turn: number,
    text: string,
    final = true,
  ): Step => ({ at, line: { id: `${role}-${turn}`, role, text, final, ts: now + at } });

  // Beat 1 — discovery, and the first quote comes from a tool.
  const discovery: Partial<LeadState> = {
    use_case: "ops team rollout",
    seat_count: 20,
    bant: { budget: 0, authority: 1, need: 2, timeline: 0 },
  };
  // Beat 3 — the seat change that has to reach the very next quote.
  const resized: Partial<LeadState> = {
    ...discovery,
    seat_count: 200,
    competitor_mentions: ["Northbeam"],
    bant: { budget: 1, authority: 2, need: 2, timeline: 1 },
    qualification: "warm",
  };
  // Beat 4 — the pricing objection, recorded rather than argued away.
  const objected: Partial<LeadState> = {
    ...resized,
    budget_signal: "stretch",
    objections_raised: ["pricing"],
  };
  // Beat 5/6 — identity arrives with the booking, and BANT crosses into hot.
  const booked: Partial<LeadState> = {
    ...objected,
    company: "Harbor Logistics",
    email: "dana@harborlogistics.com",
    industry: "freight and logistics",
    timeline: "this_quarter",
    bant: { budget: 2, authority: 2, need: 3, timeline: 2 },
    qualification: "hot",
    next_action: "book_demo",
    notes: ["Wants the enterprise walkthrough with their ops lead on the call."],
  };

  return [
    say(0, "prospect", 1, "Hi — we're looking at Vantage for our ops team. What does it run for about twenty users?"),
    tool(900, "update_lead_state", "seat_count 20, use_case ops team rollout"),
    lead(1100, discovery),
    tool(1700, "get_pricing", "Growth · 20 seats · $39 per seat / month"),
    say(2400, "agent", 1, "Growth is thirty-nine a seat at twenty seats, and that", false),
    say(3300, "agent", 1, "Growth is thirty-nine a seat at twenty seats, and that includes the shared workload views —"),

    // Beat 2 — the prospect starts before the agent has finished. The agent's line is left
    // where it was cut; it is never resumed.
    say(3900, "prospect", 2, "sorry, how does that compare to Northbeam", false),
    say(4600, "prospect", 2, "Sorry — how does that compare to Northbeam?"),
    tool(5200, "get_battlecard", "Northbeam · concedes attribution depth · wins on rollout speed"),
    say(6300, "agent", 2, "Northbeam's attribution modelling genuinely goes deeper than ours. Where we win is rollout — days, not a six-week onboarding."),

    say(8400, "prospect", 3, "Actually, it'd be closer to two hundred users."),
    tool(9000, "update_lead_state", "seat_count 20 → 200"),
    lead(9200, resized),
    tool(9800, "get_pricing", "Enterprise · 200 seats · $32 per seat / month"),
    say(10600, "agent", 3, "Two hundred puts you on Enterprise — thirty-two a seat, so six thousand four hundred a month."),

    say(12600, "prospect", 4, "That's a lot more than we budgeted."),
    tool(13100, "update_lead_state", "objection pricing, budget_signal stretch"),
    lead(13300, objected),
    say(14000, "agent", 4, "Fair. Per seat it's seven dollars cheaper than the twenty-seat price — the total moved, the unit cost came down. If this quarter's budget is fixed, we can start fifty seats and expand on the same rate."),

    say(16800, "prospect", 5, "Could we see an enterprise demo?"),
    tool(17300, "check_slots", "3 slots · Tue 10:00 · Wed 14:30 · Thu 09:00"),
    say(18100, "agent", 5, "I have Tuesday at ten, Wednesday at half two, or Thursday at nine."),
    say(19900, "prospect", 6, "Wednesday at half two. It's dana@harborlogistics.com, Harbor Logistics."),
    tool(20500, "update_lead_state", "company Harbor Logistics, email captured"),
    lead(20700, booked),
    tool(21400, "book_meeting", "Cal.com booking + HubSpot deal created"),
    {
      at: 21900,
      event: {
        type: "outcome",
        session_id: DEMO_SESSION,
        ts: now + 21900,
        data: { kind: "meeting_booked", detail: { slot: "Wed 14:30", email: "dana@harborlogistics.com" } },
      },
    },
    say(22400, "agent", 6, "Booked — Wednesday at half two. The invite is on its way to dana@harborlogistics.com."),
    {
      at: 24500,
      event: {
        type: "call_ended",
        session_id: DEMO_SESSION,
        ts: now + 24500,
        data: { duration_s: 25 },
      },
    },
  ];
}
