"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listAgents } from "@/lib/api";
import type { AgentSummary } from "@/lib/types";

export default function Agents() {
  const [agents, setAgents] = useState<AgentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listAgents()
      .then(setAgents)
      .catch((e) => setError(e instanceof Error ? e.message : "could not load agents"));
  }, []);

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-10">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold">Agents</h1>
        <Link href="/agents/new" className="rounded-md bg-emerald-600 px-4 py-2 text-sm text-white">
          New agent
        </Link>
      </div>

      {error && <p className="mt-6 text-sm text-red-600">{error}</p>}
      {!agents && !error && <p className="mt-6 text-sm text-neutral-500">Loading…</p>}
      {agents?.length === 0 && (
        <p className="mt-6 text-sm text-neutral-500">
          No agents yet. Seed the demo with{" "}
          <code className="font-mono">python -m backend.seed</code>, or create one.
        </p>
      )}

      <ul className="mt-6 divide-y divide-neutral-100 dark:divide-neutral-800">
        {agents?.map((a) => (
          <li key={a.id} className="flex items-center justify-between py-4">
            <div>
              <Link href={`/agents/${a.id}`} className="font-medium hover:underline">
                {a.name}
              </Link>
              <p className="font-mono text-xs text-neutral-500">{a.id}</p>
            </div>
            <div className="flex items-center gap-4 text-sm text-neutral-500">
              <span>{a.call_count} calls</span>
              <Link href={`/agents/${a.id}/live`} className="hover:underline">
                Live
              </Link>
              <Link href={`/agents/${a.id}/escalations`} className="hover:underline">
                Escalations
              </Link>
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
