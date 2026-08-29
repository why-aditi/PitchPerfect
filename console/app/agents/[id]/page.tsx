"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createAgent, getAgent, saveAgent } from "@/lib/api";
import type { AgentConfig } from "@/lib/types";

const TABS = ["Persona", "Knowledge", "Voice", "Integrations", "Embed"] as const;
type Tab = (typeof TABS)[number];

const BLANK: AgentConfig = {
  persona: {
    identity: "",
    greeting:
      "Hi, you're speaking with an AI sales assistant. This call is transcribed. What can I help you with?",
    goal_hierarchy: ["book a demo", "qualify with BANT", "create a follow-up", "escalate to a human"],
    objection_strategies: {
      pricing: "Reframe to per-seat value, probe the actual budget, offer a pilot. Never discount unprompted.",
      trust: "Offer a relevant proof point, a small pilot, or a human rep.",
      product: "Answer from tool data only. If the capability does not exist, say so plainly and pivot to what does.",
      competitor: "Call get_battlecard first, acknowledge one genuine strength, then position.",
    },
    escalation_triggers: ["asks for a human", "legal or security questions", "repeated frustration"],
    escalation_seat_threshold: 500,
  },
  voice: {
    tts_vendor: "",
    tts_params: {},
    speech_threshold: 0.5,
    interrupt_duration_ms: 160,
    speaking_interrupt_duration_ms: 320,
    prefix_padding_ms: 800,
    silence_duration_ms: 320,
    max_wait_ms: 3000,
    interruption_enabled: true,
    filler_phrases: ["One moment.", "Let me check that.", "Pulling that up."],
  },
  knowledge: { currency: "USD", tiers: [], battlecards: {} },
  tools_enabled: { pricing: true, battlecards: true, calendar: true, crm: true, escalation: true },
  llm_model: "llama-3.3-70b-versatile",
};

const field =
  "w-full rounded-md border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900";

export default function AgentEditor({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const isNew = id === "new";
  const router = useRouter();

  const [tab, setTab] = useState<Tab>("Persona");
  const [name, setName] = useState("");
  const [config, setConfig] = useState<AgentConfig | null>(isNew ? BLANK : null);
  const [origins, setOrigins] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    if (isNew) return;
    getAgent(id).then((a) => {
      setName(a.name);
      setConfig(a.config);
      setOrigins(a.allowed_origins.join("\n"));
    });
  }, [id, isNew]);

  if (!config) return <main className="flex-1 px-6 py-10 text-sm text-neutral-500">Loading…</main>;

  const persona = config.persona;
  const setPersona = (patch: Partial<AgentConfig["persona"]>) =>
    setConfig({ ...config, persona: { ...persona, ...patch } });

  async function save() {
    const list = origins.split("\n").map((o) => o.trim()).filter(Boolean);
    setStatus("Saving…");
    try {
      if (isNew) {
        const { id: created } = await createAgent(name, config!, list);
        router.push(`/agents/${created}`);
      } else {
        await saveAgent(id, name, config!, list);
        setStatus("Saved. The next call uses these values — no redeploy.");
      }
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "save failed");
    }
  }

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-10">
      <div className="flex items-center justify-between">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Agent name"
          className="border-0 bg-transparent text-2xl font-semibold outline-none"
        />
        {!isNew && (
          <div className="flex gap-4 text-sm text-neutral-500">
            <Link href={`/agents/${id}/live`} className="hover:underline">Live</Link>
            <Link href={`/agents/${id}/escalations`} className="hover:underline">Escalations</Link>
          </div>
        )}
      </div>

      <nav className="mt-6 flex gap-1 border-b border-neutral-200 dark:border-neutral-800">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm ${
              tab === t ? "border-b-2 border-emerald-600 font-medium" : "text-neutral-500"
            }`}
          >
            {t}
          </button>
        ))}
      </nav>

      <section className="mt-6 space-y-4">
        {tab === "Persona" && (
          <>
            <label className="block text-sm">
              Identity
              <textarea
                rows={4}
                value={persona.identity}
                onChange={(e) => setPersona({ identity: e.target.value })}
                className={`mt-1 ${field}`}
                placeholder="Who this agent sells for, in one paragraph."
              />
            </label>
            <label className="block text-sm">
              Greeting — spoken by the engine, carries the AI disclosure
              <textarea
                rows={2}
                value={persona.greeting}
                onChange={(e) => setPersona({ greeting: e.target.value })}
                className={`mt-1 ${field}`}
              />
            </label>
            {(["pricing", "trust", "product", "competitor"] as const).map((k) => (
              <label key={k} className="block text-sm capitalize">
                {k} objection
                <textarea
                  rows={2}
                  value={persona.objection_strategies[k]}
                  onChange={(e) =>
                    setPersona({
                      objection_strategies: { ...persona.objection_strategies, [k]: e.target.value },
                    })
                  }
                  className={`mt-1 ${field}`}
                />
              </label>
            ))}
            <label className="block text-sm">
              Escalate above this many seats
              <input
                type="number"
                value={persona.escalation_seat_threshold}
                onChange={(e) => setPersona({ escalation_seat_threshold: Number(e.target.value) })}
                className={`mt-1 ${field}`}
              />
            </label>
            <p className="text-xs text-neutral-500">
              Not editable, and deliberately so: never invent a price or a date, say so when a tool
              has no data, two or three sentences per turn, and drop the interrupted point rather
              than resuming it. Those are the guarantees the product makes.
            </p>
          </>
        )}

        {tab === "Knowledge" && (
          <>
            <p className="text-sm text-neutral-500">
              The only prices and competitor claims this agent may speak. Everything here is
              returned by a tool call, never recalled by the model.
            </p>
            <label className="block text-sm">
              Pricing tiers (JSON)
              <textarea
                rows={12}
                value={JSON.stringify(config.knowledge.tiers, null, 2)}
                onChange={(e) => {
                  try {
                    setConfig({
                      ...config,
                      knowledge: { ...config.knowledge, tiers: JSON.parse(e.target.value) },
                    });
                    setStatus(null);
                  } catch {
                    setStatus("Tiers: invalid JSON, not applied");
                  }
                }}
                className={`mt-1 font-mono ${field}`}
              />
            </label>
            <label className="block text-sm">
              Battlecards (JSON)
              <textarea
                rows={10}
                value={JSON.stringify(config.knowledge.battlecards, null, 2)}
                onChange={(e) => {
                  try {
                    setConfig({
                      ...config,
                      knowledge: { ...config.knowledge, battlecards: JSON.parse(e.target.value) },
                    });
                    setStatus(null);
                  } catch {
                    setStatus("Battlecards: invalid JSON, not applied");
                  }
                }}
                className={`mt-1 font-mono ${field}`}
              />
            </label>
          </>
        )}

        {tab === "Voice" && (
          <p className="text-sm text-neutral-500">
            Turn-detection and TTS tuning. Phase 7 — the values below are live and already drive
            the engine payload; the form for them is not built yet.
            <br />
            <span className="font-mono text-xs">
              speaking_interrupt_duration_ms = {config.voice.speaking_interrupt_duration_ms} · raise
              it if &quot;mm-hmm&quot; cuts the agent off
            </span>
          </p>
        )}

        {tab === "Integrations" && (
          <p className="text-sm text-neutral-500">
            Cal.com, HubSpot and Slack credentials plus per-tool switches. Phase 7. Values are
            write-only over the API and always read back as &quot;set&quot;, never as the token.
          </p>
        )}

        {tab === "Embed" && (
          <>
            <label className="block text-sm">
              Allowed origins — one per line. A call from an origin not listed here is refused.
              <textarea
                rows={4}
                value={origins}
                onChange={(e) => setOrigins(e.target.value)}
                placeholder="https://example.com"
                className={`mt-1 font-mono ${field}`}
              />
            </label>
            <label className="block text-sm">
              Embed snippet
              <textarea
                readOnly
                rows={2}
                value={
                  isNew
                    ? "Save the agent to get its snippet."
                    : `<script src="${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/embed.js?agent=${id}" async></script>`
                }
                className={`mt-1 font-mono ${field}`}
              />
            </label>
          </>
        )}
      </section>

      <div className="mt-8 flex items-center gap-4">
        <button onClick={save} className="rounded-md bg-emerald-600 px-4 py-2 text-sm text-white">
          {isNew ? "Create agent" : "Save"}
        </button>
        {status && <span className="text-sm text-neutral-500">{status}</span>}
      </div>
    </main>
  );
}
