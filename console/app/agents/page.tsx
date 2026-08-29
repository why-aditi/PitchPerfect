"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { deleteAgent, listAgents } from "@/lib/api";
import type { AgentSummary } from "@/lib/types";
import { Badge, Button, Card, Empty, cx } from "@/components/ui";

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
  "rounded-lg px-2.5 py-1.5 text-xs text-muted transition-colors hover:bg-raised hover:text-ink";

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
      className="group inline-flex items-center gap-1.5 rounded-md border border-line-soft bg-raised px-2 py-0.5 font-mono text-[11px] text-muted transition-colors hover:border-brand/50 hover:text-brand"
    >
      {id}
      <span
        className={cx(
          "text-[10px] uppercase tracking-wider transition-opacity",
          copied ? "text-listening" : "text-faint opacity-0 group-hover:opacity-100",
        )}
      >
        {copied ? "copied" : "copy"}
      </span>
    </button>
  );
}

function Meta({ label, value, dim }: { label: string; value: string; dim?: boolean }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <dt className="font-mono text-[10px] uppercase tracking-wider text-faint">{label}</dt>
      <dd className={cx("text-xs", dim ? "text-faint" : "text-ink")}>{value}</dd>
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

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold tracking-tight text-ink">Agents</h1>
            {agents && agents.length > 0 && (
              <Badge>{agents.length === 1 ? "1 agent" : `${agents.length} agents`}</Badge>
            )}
          </div>
          <p className="mt-1.5 text-sm text-muted">
            Each one carries its own persona, pricing, battlecards and integrations, and gets
            its own embed snippet.
          </p>
        </div>
        <Link
          href="/agents/new"
          className="inline-flex items-center rounded-lg bg-brand px-4 py-2 text-sm font-medium text-surface transition-colors hover:bg-brand/90"
        >
          New agent
        </Link>
      </div>

      {error && (
        <p
          role="alert"
          className="mt-6 rounded-lg border border-escalate/30 bg-escalate/5 px-3.5 py-2.5 text-sm text-escalate"
        >
          {error}
        </p>
      )}

      {!agents && !error && (
        <div className="mt-6 space-y-2.5" aria-hidden>
          {[0, 1, 2].map((i) => (
            <Card key={i} className="h-[86px] animate-pulse opacity-60" />
          ))}
        </div>
      )}

      {agents?.length === 0 && (
        <div className="mt-6">
          <Empty>
            <p className="text-ink">No agents yet.</p>
            <p className="mt-1.5">
              Seed the Vantage demo with{" "}
              <code className="rounded bg-raised px-1.5 py-0.5 font-mono text-xs text-brand">
                python -m backend.seed
              </code>
              , or build one from an empty persona.
            </p>
          </Empty>
        </div>
      )}

      <div className="mt-6 space-y-2.5">
        {agents?.map((a) => (
          <Card key={a.id} className="rise p-4 transition-colors hover:border-brand/30">
            <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2.5">
                  <Link
                    href={`/agents/${a.id}`}
                    className="text-[15px] font-medium text-ink transition-colors hover:text-brand"
                  >
                    {a.name}
                  </Link>
                  <AgentId id={a.id} />
                </div>
                <dl className="mt-2.5 flex flex-wrap items-center gap-x-5 gap-y-1">
                  <Meta label="updated" value={ago(a.updated_at)} />
                  <Meta label="calls" value={String(a.call_count)} />
                  <Meta
                    label="last outcome"
                    value={a.last_outcome_at ? ago(a.last_outcome_at) : "no outcomes yet"}
                    dim={!a.last_outcome_at}
                  />
                </dl>
              </div>

              <div className="flex items-center gap-1">
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
                    <Link href={`/agents/${a.id}`} className={ACTION}>
                      Edit
                    </Link>
                    <Link href={`/agents/${a.id}/live`} className={ACTION}>
                      Live
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
