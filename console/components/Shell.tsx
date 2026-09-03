"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { listAgents, logout } from "@/lib/api";
import { subscribe } from "@/lib/events";
import type { AgentSummary, RtmEvent } from "@/lib/types";
import { StateRing } from "./live/StateRing";
import { Mark, Nav, Wordmark } from "./Nav";
import { ThemeToggle } from "./theme";
import { Button, Dot, cx } from "./ui";

/**
 * The console's frame: a persistent sidebar listing every agent, with the open agent
 * expanded into its sections, and a docked strip on the right that follows the open
 * agent's live call. Login and the embed widget render outside it.
 */

export const SECTIONS = ["Persona", "Knowledge", "Voice", "Integrations", "Embed"] as const;
export type Section = (typeof SECTIONS)[number];

const SECTION_NOTE: Record<Section, string> = {
  Persona: "who it is",
  Knowledge: "what it may say",
  Voice: "how it listens",
  Integrations: "where it writes",
  Embed: "where it runs",
};

/** Reads ?tab= and falls back to the first section; the sidebar writes the same param. */
export function useSection(): Section {
  const raw = useSearchParams().get("tab");
  return (SECTIONS as readonly string[]).includes(raw ?? "") ? (raw as Section) : "Persona";
}

/* ---------------------------------------------------------------- data */

function useBackend(): "up" | "down" | null {
  const [state, setState] = useState<"up" | "down" | null>(null);
  useEffect(() => {
    let alive = true;
    const probe = async () => {
      try {
        const r = await fetch("/api/openapi.json", { method: "HEAD", cache: "no-store" });
        if (alive) setState(r.ok ? "up" : "down");
      } catch {
        if (alive) setState("down");
      }
    };
    void probe();
    const t = setInterval(probe, 30_000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);
  return state;
}

type Feed = {
  phase: "idle" | "live" | "ended";
  session: string | null;
  lastTool: string | null;
  outcome: string | null;
  escalations: number;
};

const OUTCOME_LABEL = {
  meeting_booked: "Meeting booked",
  lead_qualified: "Lead qualified",
  escalated: "Escalated to a rep",
} as const;

/**
 * Everything the frame needs to know about the open agent's call, from the event stream
 * alone. No channel is joined here — that costs a token and belongs to the Live page.
 */
function useFeed(agentId: string | null): Feed {
  const [feed, setFeed] = useState<Feed>({ phase: "idle", session: null, lastTool: null, outcome: null, escalations: 0 });
  const session = useRef<string | null>(null);

  useEffect(() => {
    session.current = null;
    // Reset off the synchronous path so the subscription and the reset land together.
    const reset = requestAnimationFrame(() =>
      setFeed({ phase: "idle", session: null, lastTool: null, outcome: null, escalations: 0 }),
    );
    if (!agentId || agentId === "new") return () => cancelAnimationFrame(reset);
    const off = subscribe(agentId, (e: RtmEvent) => {
      setFeed((f) => {
        const fresh = session.current !== e.session_id;
        session.current = e.session_id;
        const base: Feed = fresh
          ? { phase: "live", session: e.session_id, lastTool: null, outcome: null, escalations: f.escalations }
          : { ...f, phase: f.phase === "ended" ? "live" : f.phase };
        switch (e.type) {
          case "tool_call":
            return { ...base, lastTool: e.data.name };
          case "outcome":
            return { ...base, outcome: OUTCOME_LABEL[e.data.kind] };
          case "escalation":
            return { ...base, escalations: base.escalations + 1 };
          case "call_ended":
            return { ...base, phase: "ended" };
          default:
            return base;
        }
      });
    });
    return () => {
      cancelAnimationFrame(reset);
      off();
    };
  }, [agentId]);

  return feed;
}

/* ---------------------------------------------------------------- shell */

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "";
  const router = useRouter();

  const bare = pathname === "/login" || pathname.startsWith("/widget");

  const m = pathname.match(/^\/agents\/([^/]+)(?:\/(live|escalations))?/);
  const agentId = m?.[1] ?? null;
  const sub = m?.[2] ?? "";
  const section = useSection();

  // null: not loaded yet; false: could not load (the page shows the reason, not the sidebar).
  const [agents, setAgents] = useState<AgentSummary[] | null | false>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const backend = useBackend();
  const feed = useFeed(agentId);

  // The list is cheap and the sidebar is the one place a rename or a delete must show up
  // immediately, so it refreshes on every route change rather than caching.
  useEffect(() => {
    if (bare) return;
    listAgents().then(setAgents).catch(() => setAgents(false));
  }, [pathname, bare]);

  useEffect(() => {
    const id = requestAnimationFrame(() => setOpen(false));
    return () => cancelAnimationFrame(id);
  }, [pathname]);

  if (bare) {
    return (
      <>
        <Nav />
        {children}
      </>
    );
  }

  async function signOut() {
    setBusy(true);
    try {
      await logout();
    } catch {
      /* already gone, or the backend is down */
    }
    router.push("/login");
  }

  const current = (agents || []).find((a) => a.id === agentId) ?? null;

  const sidebar = (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-line bg-panel">
      <div className="flex h-16 shrink-0 items-center justify-between border-b border-line px-5">
        <Link href="/agents" className="flex items-center gap-2.5 transition-opacity hover:opacity-80">
          <Mark className="h-8 w-8 text-brand" />
          <Wordmark className="text-[17px]" />
        </Link>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label="Close menu"
          className="rounded-md p-1 text-muted hover:bg-raised hover:text-ink lg:hidden"
        >
          <Close />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
        <div className="mb-2 flex items-center justify-between px-2">
          <Link href="/agents" className={cx("text-xs font-medium", pathname === "/agents" ? "text-ink" : "text-faint hover:text-ink")}>
            Agents
          </Link>
          <Link href="/agents/new" className="rounded-md px-1.5 py-0.5 text-xs text-muted transition-colors hover:bg-raised hover:text-ink">
            + New
          </Link>
        </div>

        {agents === null && (
          <div className="space-y-1.5 px-1" aria-hidden>
            {[0, 1, 2].map((i) => <div key={i} className="h-8 animate-pulse rounded-lg bg-raised" />)}
          </div>
        )}

        {agents !== null && agents !== false && agents.length === 0 && (
          <p className="px-2.5 py-2 text-xs leading-relaxed text-faint">No agents yet. Create one to get started.</p>
        )}

        <ul className="space-y-0.5">
          {agentId === "new" && (
            <li>
              <span className="flex items-center gap-2.5 rounded-lg bg-raised px-2.5 py-2 text-sm text-ink">
                <span className="h-1.5 w-1.5 rounded-full bg-line" />
                <span className="flex-1 truncate">New agent</span>
              </span>
            </li>
          )}
          {agents && agents.map((a) => {
            const active = a.id === agentId;
            const live = active && feed.phase === "live";
            return (
              <li key={a.id}>
                <Link
                  href={`/agents/${a.id}`}
                  className={cx(
                    "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors",
                    active ? "bg-raised text-ink" : "text-muted hover:bg-raised hover:text-ink",
                  )}
                >
                  <span className={cx("h-1.5 w-1.5 shrink-0 rounded-full", live ? "bg-listening" : "bg-line")} />
                  <span className="flex-1 truncate">{a.name}</span>
                  {live && <span className="text-[11px] text-listening">live</span>}
                </Link>

                {active && (
                  <ul className="mb-2 mt-1 ml-4 space-y-0.5 border-l border-line pl-3">
                    {SECTIONS.map((s) => {
                      const on = !sub && section === s;
                      return (
                        <li key={s}>
                          <Link
                            href={`/agents/${a.id}?tab=${s}`}
                            aria-current={on ? "page" : undefined}
                            className={cx(
                              "flex items-center justify-between rounded-md px-2 py-1.5 text-[13px] transition-colors",
                              on ? "bg-panel text-ink shadow-sm ring-1 ring-line" : "text-muted hover:text-ink",
                            )}
                          >
                            {s}
                            <span className="text-[11px] text-faint">{SECTION_NOTE[s]}</span>
                          </Link>
                        </li>
                      );
                    })}
                    <li className="pt-1">
                      <Link
                        href={`/agents/${a.id}/live`}
                        aria-current={sub === "live" ? "page" : undefined}
                        className={cx(
                          "flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px] transition-colors",
                          sub === "live" ? "bg-panel text-ink shadow-sm ring-1 ring-line" : "text-muted hover:text-ink",
                        )}
                      >
                        <span className={cx("h-1.5 w-1.5 rounded-full", live ? "bg-listening" : "bg-line")} />
                        Live call
                      </Link>
                    </li>
                    <li>
                      <Link
                        href={`/agents/${a.id}/escalations`}
                        aria-current={sub === "escalations" ? "page" : undefined}
                        className={cx(
                          "flex items-center justify-between rounded-md px-2 py-1.5 text-[13px] transition-colors",
                          sub === "escalations" ? "bg-panel text-ink shadow-sm ring-1 ring-line" : "text-muted hover:text-ink",
                        )}
                      >
                        Escalations
                        {feed.escalations > 0 && (
                          <span className="rounded-full bg-escalate/12 px-1.5 text-[11px] text-escalate">{feed.escalations}</span>
                        )}
                      </Link>
                    </li>
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </div>

      <div className="shrink-0 space-y-2 border-t border-line p-3">
        <div className="flex items-center gap-2 px-2 text-xs text-muted">
          <Dot
            tone={backend === "up" ? "var(--color-listening)" : backend === "down" ? "var(--color-escalate)" : "var(--color-faint)"}
            pulse={backend === "up"}
          />
          {backend === "up" ? "Backend online" : backend === "down" ? "Backend offline" : "Checking backend"}
        </div>
        <div className="flex items-center justify-between px-1">
          <ThemeToggle />
          <Button variant="quiet" onClick={signOut} disabled={busy} className="px-2.5 py-1.5 text-xs">
            {busy ? "Signing out…" : "Sign out"}
          </Button>
        </div>
      </div>
    </aside>
  );

  return (
    <div className="flex h-screen overflow-hidden">
      <div className="hidden lg:block">{sidebar}</div>

      {open && (
        <div className="fixed inset-0 z-40 flex lg:hidden">
          <div className="h-full">{sidebar}</div>
          <button type="button" aria-label="Close menu" className="flex-1 bg-ink/40" onClick={() => setOpen(false)} />
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Small screens: the sidebar is a drawer behind this bar. */}
        <div className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-panel px-4 lg:hidden">
          <button type="button" onClick={() => setOpen(true)} aria-label="Open menu" className="rounded-md p-1.5 text-muted hover:bg-raised hover:text-ink">
            <Menu />
          </button>
          <Mark className="h-7 w-7 text-brand" />
          <span className="truncate text-sm text-ink">{current?.name ?? (agentId === "new" ? "New agent" : "Agents")}</span>
        </div>

        <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
      </div>

      {agentId && agentId !== "new" && !sub && (
        <aside className="hidden w-72 shrink-0 flex-col border-l border-line bg-panel xl:flex">
          <div className="flex h-16 shrink-0 items-center gap-3 border-b border-line px-5">
            <StateRing state={feed.phase === "live" ? "listening" : "idle"} size={36} />
            <div className="min-w-0">
              <p className="text-sm font-medium text-ink">
                {feed.phase === "live" ? "Call in progress" : feed.phase === "ended" ? "Call ended" : "No call"}
              </p>
              <p className="truncate font-mono text-[11px] text-faint">{feed.session ?? "waiting"}</p>
            </div>
          </div>
          <div className="space-y-4 p-5 text-[13px] leading-snug">
            {feed.phase === "idle" ? (
              <p className="text-muted">
                This strip follows the open agent. When a call starts, the latest tool call and outcome show here.
              </p>
            ) : (
              <>
                <div>
                  <p className="text-xs font-medium text-faint">Last tool call</p>
                  <p className="mt-0.5 font-mono text-xs text-brand">{feed.lastTool ?? "none yet"}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-faint">Outcome</p>
                  <p className="mt-0.5 text-ink">{feed.outcome ?? "not yet"}</p>
                </div>
              </>
            )}
            <Link
              href={`/agents/${agentId}/live`}
              className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-panel px-3 py-1.5 text-xs text-ink transition-colors hover:border-ink/40"
            >
              Open live view
            </Link>
          </div>
        </aside>
      )}
    </div>
  );
}

function Menu() {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <path d="M2.5 4h11M2.5 8h11M2.5 12h11" />
    </svg>
  );
}

function Close() {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <path d="M4 4l8 8M12 4l-8 8" />
    </svg>
  );
}
