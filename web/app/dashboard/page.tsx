"use client";

import { useEffect, useRef, useState } from "react";
import { subscribe } from "@/lib/events";
import type { LeadState, RtmEvent } from "@/lib/types";

type ToolCall = { name: string; result_summary: string; ts: number };

export default function Dashboard() {
  const [lead, setLead] = useState<LeadState | null>(null);
  const [tools, setTools] = useState<ToolCall[]>([]);
  const [changed, setChanged] = useState<string[]>([]);
  const previous = useRef<LeadState | null>(null);

  useEffect(
    () =>
      subscribe((e: RtmEvent) => {
        if (e.type === "lead_state") {
          const before = previous.current;
          setChanged(
            before
              ? Object.keys(e.data).filter(
                  (k) =>
                    JSON.stringify(e.data[k as keyof LeadState]) !==
                    JSON.stringify(before[k as keyof LeadState]),
                )
              : [],
          );
          previous.current = e.data;
          setLead(e.data);
        }
        if (e.type === "tool_call") {
          setTools((t) => [{ ...e.data, ts: e.ts }, ...t].slice(0, 20));
        }
      }),
    [],
  );

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-10">
      <h1 className="text-2xl font-semibold">Live call</h1>

      <h2 className="mt-8 mb-2 text-sm uppercase tracking-wide text-neutral-500">Lead state</h2>
      {!lead ? (
        <p className="text-sm text-neutral-500">
          No active session. The backend publishes these over RTM on{" "}
          <code className="font-mono">&lt;channel&gt;-events</code>.
        </p>
      ) : (
        <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
          {Object.entries(lead).map(([k, v]) => (
            <div
              key={k}
              className={`flex justify-between border-b border-neutral-100 py-1 text-sm dark:border-neutral-800 ${
                changed.includes(k) ? "bg-amber-100 dark:bg-amber-900/40" : ""
              }`}
            >
              <dt className="text-neutral-500">{k}</dt>
              <dd className="font-mono">
                {Array.isArray(v) ? v.join(", ") || "—" : JSON.stringify(v)}
              </dd>
            </div>
          ))}
        </dl>
      )}

      <h2 className="mt-8 mb-2 text-sm uppercase tracking-wide text-neutral-500">Tool calls</h2>
      <div className="flex flex-wrap gap-2">
        {tools.length === 0 && <span className="text-sm text-neutral-500">None yet.</span>}
        {tools.map((t) => (
          <span
            key={t.ts + t.name}
            className="rounded-full bg-neutral-100 px-3 py-1 font-mono text-xs dark:bg-neutral-800"
          >
            {t.name} → {t.result_summary}
          </span>
        ))}
      </div>

      <h2 className="mt-8 mb-2 text-sm uppercase tracking-wide text-neutral-500">Transcript</h2>
      <p className="text-sm text-neutral-500">
        Rendered from the engine&apos;s own transcript stream, not from our RTM events (PRD 6.2).
      </p>
    </main>
  );
}
