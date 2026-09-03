"use client";

import type { ReactNode } from "react";
import { cx } from "@/components/ui";
import type { LeadState } from "@/lib/types";

/**
 * Lead state (PRD §7), grouped the way a rep reads it rather than as a key dump: who they
 * are, what the deal looks like, what is in the way, and what that adds up to.
 *
 * `version` counts lead_state events. It is part of every flashed key so the element
 * remounts and the one-shot highlight replays — a changed value that does not flash reads
 * as unchanged.
 */
export function LeadPanel({
  lead,
  changed,
  version,
}: {
  lead: LeadState | null;
  changed: readonly string[];
  version: number;
}) {
  if (!lead) {
    return (
      <div className="rounded-xl border border-dashed border-line px-5 py-8 text-sm leading-relaxed text-muted">
        No lead state yet. The agent publishes one on every{" "}
        <code className="font-mono text-xs text-ink">update_lead_state</code> call, so this
        fills in as the prospect answers — company first, then seats, then BANT.
      </div>
    );
  }

  const flash = (key: string) => changed.includes(key);
  const bantSum =
    lead.bant.budget + lead.bant.authority + lead.bant.need + lead.bant.timeline;

  return (
    <div className="space-y-5">
      <Group title="Identity">
        <Row label="Company" flash={flash("company")} version={version} value={lead.company} />
        <Row label="Email" flash={flash("email")} version={version} value={lead.email} mono />
        <Row label="Industry" flash={flash("industry")} version={version} value={lead.industry} />
        <Row label="Use case" flash={flash("use_case")} version={version} value={lead.use_case} />
      </Group>

      <Group title="Deal shape">
        <Row
          label="Seats"
          flash={flash("seat_count")}
          version={version}
          value={lead.seat_count === null ? null : lead.seat_count.toLocaleString()}
          mono
        />
        <Row
          label="Budget signal"
          flash={flash("budget_signal")}
          version={version}
          value={words(lead.budget_signal)}
        />
        <Row
          label="Timeline"
          flash={flash("timeline")}
          version={version}
          value={words(lead.timeline)}
        />
      </Group>

      <Group title="Friction">
        <ChipRow
          label="Objections"
          items={lead.objections_raised}
          tone="escalate"
          flash={flash("objections_raised")}
          version={version}
        />
        <ChipRow
          label="Competitors"
          items={lead.competitor_mentions}
          tone="thinking"
          flash={flash("competitor_mentions")}
          version={version}
        />
        {/* Not a ChipRow. Every other item in this panel is a word — "pricing",
            "Northbeam" — and these are sentences, so pills read as a wall. Numbered and
            stacked because the order is the point: a rep reading this needs to see the
            ladder being climbed, and which rung the call stopped on. */}
        <Conceded items={lead.concessions_offered} flash={flash("concessions_offered")}
                  version={version} />
      </Group>

      <Group title="Qualification">
        <div
          key={`bant-${flash("bant") ? version : "steady"}`}
          className={cx("rounded-lg px-2 py-1.5", flash("bant") && "flash")}
        >
          {(["budget", "authority", "need", "timeline"] as const).map((k) => (
            <Bant key={k} label={k} score={lead.bant[k]} tone={lead.qualification} />
          ))}
        </div>

        <div className="flex items-center justify-between px-2 pt-1">
          <span
            key={`qual-${flash("qualification") ? version : "steady"}`}
            className={cx(
              "inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium capitalize",
              QUAL[lead.qualification],
              flash("qualification") && "flash",
            )}
          >
            {lead.qualification}
          </span>
          <span className="font-mono text-xs text-faint">BANT {bantSum}/12</span>
        </div>

        <Row
          label="Next action"
          flash={flash("next_action")}
          version={version}
          value={words(lead.next_action)}
        />
      </Group>

      {lead.notes.length > 0 && (
        <Group title="Notes">
          <ul className="space-y-1.5 px-2">
            {lead.notes.map((n, i) => (
              <li key={`${i}-${n}`} className="text-sm leading-snug text-muted">
                {n}
              </li>
            ))}
          </ul>
        </Group>
      )}
    </div>
  );
}

const QUAL: Record<LeadState["qualification"], string> = {
  cold: "bg-raised text-muted",
  warm: "bg-thinking/12 text-thinking",
  hot: "bg-listening/12 text-listening",
};

const BAR: Record<LeadState["qualification"], string> = {
  cold: "bg-muted",
  warm: "bg-thinking",
  hot: "bg-listening",
};

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-1.5 text-xs font-medium text-faint">
        {title}
      </h3>
      <div className="space-y-0.5">{children}</div>
    </section>
  );
}

function Row({
  label,
  value,
  flash,
  version,
  mono,
}: {
  label: string;
  value: string | null;
  flash: boolean;
  version: number;
  mono?: boolean;
}) {
  return (
    <div
      key={`${label}-${flash ? version : "steady"}`}
      className={cx(
        "flex items-baseline justify-between gap-4 rounded-md px-2 py-1",
        flash && "flash",
      )}
    >
      <span className="text-sm text-muted">{label}</span>
      <span
        className={cx(
          "truncate text-right text-sm",
          mono && "font-mono text-[13px]",
          value === null ? "text-faint" : "text-ink",
        )}
      >
        {value ?? "—"}
      </span>
    </div>
  );
}

/**
 * What the call has committed to, in the order it was given.
 *
 * These are the only entries in this panel that are promises rather than observations —
 * everything else here is something the prospect said, and this is something the company
 * now owes. A rep who picks up an escalation reads it to find out what they have already
 * been committed to, so it stays legible when empty as well as when full.
 */
function Conceded({
  items,
  flash,
  version,
}: {
  items: string[];
  flash: boolean;
  version: number;
}) {
  return (
    <div
      key={`conceded-${flash ? version : "steady"}`}
      className={cx("rounded-md px-2 py-1", flash && "flash")}
    >
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-sm text-muted">Conceded</span>
        {items.length === 0 && <span className="text-sm text-faint">nothing given</span>}
      </div>
      {items.length > 0 && (
        <ol className="mt-1.5 space-y-1">
          {items.map((given, i) => (
            <li key={given} className="flex gap-2 text-xs leading-snug text-listening">
              <span className="font-mono text-faint tabular-nums">{i + 1}</span>
              <span>{given}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function ChipRow({
  label,
  items,
  tone,
  flash,
  version,
}: {
  label: string;
  items: string[];
  tone: "escalate" | "thinking" | "listening";
  flash: boolean;
  version: number;
}) {
  const chip =
    tone === "escalate"
      ? "bg-escalate/12 text-escalate"
      : tone === "listening"
        ? "bg-listening/12 text-listening"
        : "bg-thinking/12 text-thinking";
  return (
    <div
      key={`${label}-${flash ? version : "steady"}`}
      className={cx(
        "flex items-baseline justify-between gap-4 rounded-md px-2 py-1",
        flash && "flash",
      )}
    >
      <span className="text-sm text-muted">{label}</span>
      {items.length === 0 ? (
        <span className="text-sm text-faint">none</span>
      ) : (
        <span className="flex flex-wrap justify-end gap-1.5">
          {items.map((i) => (
            <span
              key={i}
              className={cx(
                "rounded-full px-2 py-0.5 text-xs",
                chip,
              )}
            >
              {i}
            </span>
          ))}
        </span>
      )}
    </div>
  );
}

function Bant({
  label,
  score,
  tone,
}: {
  label: string;
  score: number;
  tone: LeadState["qualification"];
}) {
  return (
    <div className="flex items-center gap-3 py-[3px]">
      <span className="w-16 text-xs capitalize text-muted">
        {label}
      </span>
      <span className="flex flex-1 gap-1">
        {[1, 2, 3].map((step) => (
          <span
            key={step}
            className={cx(
              "h-1.5 flex-1 rounded-full transition-colors",
              step <= score ? BAR[tone] : "bg-line",
            )}
          />
        ))}
      </span>
      <span className="w-4 text-right font-mono text-[11px] text-faint">{score}</span>
    </div>
  );
}

/** The lead state stores enum-ish snake_case; a rep reads prose. */
function words(value: string | null): string | null {
  return value === null ? null : value.replace(/_/g, " ");
}
