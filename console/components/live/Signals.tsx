"use client";

import { cx } from "@/components/ui";

export type ToolCall = { name: string; result_summary: string; ts: number };
export type Outcome = { kind: "meeting_booked" | "lead_qualified" | "escalated"; ts: number };

/**
 * The agent's work, newest first. Grounding is the claim being judged (PRD G3): every
 * price and slot in the transcript should have a chip here that produced it.
 */
export function ToolChips({ calls }: { calls: ToolCall[] }) {
  if (calls.length === 0) {
    return (
      <p className="text-sm text-muted">
        Nothing called yet. Prices, availability and competitor claims only reach the
        prospect through a tool, so each one shows up here first.
      </p>
    );
  }

  return (
    <ol className="space-y-1.5">
      {calls.map((c) => (
        <li
          key={`${c.ts}-${c.name}`}
          className="rise flex items-baseline gap-2 rounded-lg bg-raised px-2.5 py-1.5"
        >
          <span className="font-mono text-xs text-brand">{c.name}</span>
          <span className="min-w-0 flex-1 truncate text-[13px] text-ink" title={c.result_summary}>
            {c.result_summary}
          </span>
          <span className="shrink-0 font-mono text-[10px] text-faint">{at(c.ts)}</span>
        </li>
      ))}
    </ol>
  );
}

const OUTCOME: Record<Outcome["kind"], { label: string; tone: string }> = {
  meeting_booked: { label: "Meeting booked", tone: "bg-listening/12 text-listening" },
  lead_qualified: { label: "Lead qualified", tone: "bg-brand-soft text-brand" },
  escalated: { label: "Escalated to a rep", tone: "bg-escalate/12 text-escalate" },
};

/** PRD G5: a call ends with a booking, a qualified lead or an escalation — never a dead end. */
export function Outcomes({
  outcomes,
  endedAfter,
}: {
  outcomes: Outcome[];
  endedAfter: number | null;
}) {
  if (outcomes.length === 0 && endedAfter === null) return null;

  return (
    <div className="space-y-2">
      {outcomes.map((o) => (
        <div
          key={`${o.ts}-${o.kind}`}
          className={cx(
            "rise flex items-center justify-between rounded-lg px-3 py-2",
            OUTCOME[o.kind].tone,
          )}
        >
          <span className="text-sm font-medium">{OUTCOME[o.kind].label}</span>
          <span className="font-mono text-[10px] text-faint">{at(o.ts)}</span>
        </div>
      ))}
      {endedAfter !== null && (
        <p className="px-1 text-xs text-faint">
          Call ended after {Math.floor(endedAfter / 60)}m {endedAfter % 60}s
        </p>
      )}
    </div>
  );
}

const at = (ts: number) =>
  new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
