"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { deleteAgent, listAgents } from "@/lib/api";
import type { AgentSummary } from "@/lib/types";
import { Button, Card, Empty, cx } from "@/components/ui";

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/**
 * Relative time, to the coarsest unit that still answers "is this stale?". No date library
 * is installed and none is worth adding for two timestamps on one screen.
 */
function ago(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "unknown";
  const d = Date.now() - t;
  if (d < MINUTE) return "just now";
  if (d < HOUR) return `${Math.floor(d / MINUTE)}m ago`;
  if (d < DAY) return `${Math.floor(d / HOUR)}h ago`;
  if (d < 30 * DAY) return `${Math.floor(d / DAY)}d ago`;
  return new Date(t).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

const message = (e: unknown) => (e instanceof Error ? e.message : "unknown error");

const ACTION =
  "rounded-md px-2.5 py-1.5 text-xs text-muted transition-colors hover:bg-raised hover:text-ink";

/** The id goes in the embed snippet, so it is copied far more often than it is read. */
function AgentId({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => () => clearTimeout(timer.current), []);

  async function copy() {
    try {
      await navigator.clipboard.writeText(id);
    } catch {
      return; // Denied, or a non-secure origin. Say nothing rather than claim a copy.
    }
    setCopied(true);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 1400);
  }

  return (
    <button
      type="button"
      onClick={copy}
      aria-label={`Copy agent id ${id}`}
      className="group inline-flex items-center gap-1.5 rounded-md bg-raised px-2 py-0.5 font-mono text-[12px] text-muted transition-colors hover:text-ink"
    >
      {id}
      <span
        className={cx(
          "text-[11px] transition-opacity",
          copied ? "text-listening opacity-100" : "text-faint opacity-0 group-hover:opacity-100",
        )}
      >
        {copied ? "copied" : "copy"}
      </span>
    </button>
  );
}

function Stat({ label, value, dim }: { label: string; value: string; dim?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-faint">{label}</dt>
      <dd className={cx("mt-0.5 truncate text-sm", dim ? "text-faint" : "text-ink")}>{value}</dd>
    </div>
  );
}

export default function Agents() {
  const [agents, setAgents] = useState<AgentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);

  useEffect(() => {
    listAgents()
      .then(setAgents)
      .catch((e) => setError(message(e)));
  }, []);

  async function remove(agent: AgentSummary) {
    setConfirming(null);
    setError(null);
    const index = agents?.findIndex((a) => a.id === agent.id) ?? 0;
    setAgents((cur) => cur?.filter((a) => a.id !== agent.id) ?? cur);
    try {
      await deleteAgent(agent.id);
    } catch (e) {
      // Restore at the original index: the list is ordered by updated_at, so appending
      // would leave the row in a position the next reload silently contradicts.
      setAgents((cur) => {
        if (!cur) return cur;
        const next = [...cur];
        next.splice(Math.max(index, 0), 0, agent);
        return next;
      });
      setError(`Could not delete ${agent.name} — ${message(e)}`);
    }
  }

  const calls = agents?.reduce((n, a) => n + a.call_count, 0) ?? 0;

  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-8 lg:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight text-ink">Agents</h1>
          <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted">
            Each one carries its own persona, pricing, battlecards and integrations, and gets
            its own embed snippet.
          </p>
        </div>
        <Link
          href="/agents/new"
          className="inline-flex items-center gap-2 rounded-lg bg-ink px-4 py-2 text-sm font-medium text-surface transition-colors hover:bg-ink/85"
        >
          <Plus />
          New agent
        </Link>
      </div>

      {agents && agents.length > 0 && (
        <dl className="mt-8 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-4">
          <Tile label="Agents" value={String(agents.length)} />
          <Tile label="Calls handled" value={calls.toLocaleString()} />
          <Tile
            label="Last updated"
            value={ago(agents.map((a) => a.updated_at).sort().at(-1) ?? "")}
          />
          <Tile
            label="Last outcome"
            value={
              agents.some((a) => a.last_outcome_at)
                ? ago(
                    agents
                      .map((a) => a.last_outcome_at)
                      .filter((x): x is string => Boolean(x))
                      .sort()
                      .at(-1) ?? "",
                  )
                : "none yet"
            }
          />
        </dl>
      )}

      {error && (
        <p
          role="alert"
          className="mt-6 rounded-lg border border-escalate/30 bg-escalate/5 px-3.5 py-2.5 text-sm text-escalate"
        >
          {error}
        </p>
      )}

      {!agents && !error && (
        <div className="mt-8 space-y-2.5" aria-hidden>
          {[0, 1, 2].map((i) => (
            <Card key={i} className="h-[92px] animate-pulse opacity-60" />
          ))}
        </div>
      )}

      {agents?.length === 0 && (
        <div className="mt-8">
          <Empty>
            <p className="font-display text-base font-semibold text-ink">No agents yet</p>
            <p className="mx-auto mt-1.5 max-w-md">
              An agent is a persona, a price list and a script tag. Create one from scratch, or
              seed the Vantage demo from the backend with{" "}
              <code className="rounded bg-raised px-1.5 py-0.5 font-mono text-xs text-ink">
                python -m backend.seed
              </code>
              .
            </p>
            <Link
              href="/agents/new"
              className="mt-5 inline-flex items-center gap-2 rounded-lg bg-ink px-4 py-2 text-sm font-medium text-surface transition-colors hover:bg-ink/85"
            >
              Create your first agent
            </Link>
          </Empty>
        </div>
      )}

      <div className="mt-8 space-y-2.5">
        {agents?.map((a) => (
          <Card
            key={a.id}
            className="rise relative p-5 transition-colors hover:border-faint focus-within:border-brand"
          >
            <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-3">
                  {/* The stretched link makes the whole card the target; the buttons on the
                      right sit above it so they still get their own clicks. */}
                  <Link
                    href={`/agents/${a.id}`}
                    className="font-display text-lg font-semibold text-ink transition-colors after:absolute after:inset-0 after:rounded-xl hover:text-brand"
                  >
                    {a.name}
                  </Link>
                  <AgentId id={a.id} />
                </div>
                <dl className="mt-3 grid max-w-md grid-cols-3 gap-4">
                  <Stat label="Updated" value={ago(a.updated_at)} />
                  <Stat label="Calls" value={String(a.call_count)} />
                  <Stat
                    label="Last outcome"
                    value={a.last_outcome_at ? ago(a.last_outcome_at) : "none yet"}
                    dim={!a.last_outcome_at}
                  />
                </dl>
              </div>

              <div className="relative z-10 flex items-center gap-1">
                {confirming === a.id ? (
                  <span className="flex items-center gap-1.5 rounded-lg border border-escalate/30 bg-escalate/5 py-1 pl-2.5 pr-1">
                    <span className="text-xs text-muted">Delete this agent and its calls?</span>
                    <Button
                      variant="danger"
                      className="border-transparent px-2 py-1 text-xs"
                      onClick={() => remove(a)}
                    >
                      Delete
                    </Button>
                    <Button
                      variant="quiet"
                      className="px-2 py-1 text-xs"
                      onClick={() => setConfirming(null)}
                    >
                      Cancel
                    </Button>
                  </span>
                ) : (
                  <>
                    <Link
                      href={`/agents/${a.id}/live`}
                      className="mr-1 inline-flex items-center gap-1.5 rounded-lg border border-line bg-panel px-3 py-1.5 text-xs text-ink transition-colors hover:border-ink/40"
                    >
                      <span className="h-1.5 w-1.5 rounded-full bg-listening" />
                      Watch live
                    </Link>
                    <Link href={`/agents/${a.id}`} className={ACTION}>
                      Edit
                    </Link>
                    <Link href={`/agents/${a.id}/escalations`} className={ACTION}>
                      Escalations
                    </Link>
                    <Button
                      variant="quiet"
                      className="px-2.5 py-1.5 text-xs hover:text-escalate"
                      onClick={() => setConfirming(a.id)}
                    >
                      Delete
                    </Button>
                  </>
                )}
              </div>
            </div>
          </Card>
        ))}
      </div>
    </main>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-panel px-5 py-4">
      <dt className="text-xs text-faint">{label}</dt>
      <dd className="mt-1 font-display text-2xl font-semibold tracking-tight text-ink">{value}</dd>
    </div>
  );
}

function Plus() {
  return (
    <svg viewBox="0 0 14 14" aria-hidden className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
      <path d="M7 2.5v9M2.5 7h9" />
    </svg>
  );
}
