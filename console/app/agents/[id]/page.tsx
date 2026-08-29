"use client";

import { use, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createAgent, getAgent, saveAgent, saveSecrets } from "@/lib/api";
import type { AgentConfig, Knowledge, Persona, SecretsSet, ToolsEnabled, Voice } from "@/lib/types";
import { Badge, Button, Tabs } from "@/components/ui";
import { EmbedTab, originError } from "@/components/editor/EmbedTab";
import { IntegrationsTab, type SecretDraft } from "@/components/editor/IntegrationsTab";
import { KnowledgeTab } from "@/components/editor/KnowledgeTab";
import { PersonaTab } from "@/components/editor/PersonaTab";
import { VoiceTab } from "@/components/editor/VoiceTab";

const TABS = ["Persona", "Knowledge", "Voice", "Integrations", "Embed"] as const;
type Tab = (typeof TABS)[number];

/** A new agent starts from the same defaults models.py would have given it. */
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

/** What "unsaved" is measured against: the shape the server last confirmed. */
type Snapshot = { name: string; config: AgentConfig; origins: string[] };
const fingerprint = (s: Snapshot) => JSON.stringify(s);

export default function AgentEditor({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const isNew = id === "new";
  const router = useRouter();

  const [tab, setTab] = useState<Tab>("Persona");
  const [name, setName] = useState("");
  const [config, setConfig] = useState<AgentConfig | null>(isNew ? BLANK : null);
  const [origins, setOrigins] = useState<string[]>([]);
  const [secrets, setSecrets] = useState<SecretsSet | null>(null);
  const [secretDraft, setSecretDraft] = useState<SecretDraft>({});
  const [saved, setSaved] = useState<string>(() =>
    isNew ? fingerprint({ name: "", config: BLANK, origins: [] }) : "",
  );

  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isNew) return;
    getAgent(id)
      .then((a) => {
        setName(a.name);
        setConfig(a.config);
        setOrigins(a.allowed_origins);
        setSecrets(a.secrets_set);
        setSaved(fingerprint({ name: a.name, config: a.config, origins: a.allowed_origins }));
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : "could not load this agent"));
  }, [id, isNew]);

  const current = useMemo(
    () => (config ? fingerprint({ name, config, origins }) : ""),
    [name, config, origins],
  );
  const configDirty = Boolean(config) && current !== saved;
  const secretsDirty = Object.keys(secretDraft).length > 0;
  const dirty = configDirty || secretsDirty;

  // Config is read fresh on every call, so an unsaved edit is an edit that is not live.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  /** Every tab owns one section of the config and patches only that section. */
  const patchConfig = useCallback(
    <K extends "persona" | "voice" | "knowledge" | "tools_enabled">(
      key: K,
      patch: Partial<AgentConfig[K]>,
    ) => setConfig((c) => (c ? { ...c, [key]: { ...(c[key] as object), ...patch } } : c)),
    [],
  );

  const setSecretField = useCallback(
    (key: string, value: string | null | undefined) =>
      setSecretDraft((d) => {
        const next = { ...d };
        if (value === undefined) delete next[key];
        else next[key] = value;
        return next;
      }),
    [],
  );

  if (loadError) {
    return (
      <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-10">
        <p className="rounded-xl border border-escalate/30 bg-escalate/5 px-4 py-3 text-sm text-escalate">
          {loadError}
        </p>
        <Link href="/agents" className="mt-4 inline-block text-sm text-muted hover:text-ink">
          Back to agents
        </Link>
      </main>
    );
  }

  if (!config) {
    return <main className="flex-1 px-6 py-10 text-sm text-muted">Loading…</main>;
  }

  const badOrigin = origins.some((o) => o.trim() && originError(o));
  const blocked = !name.trim()
    ? "Give the agent a name first."
    : badOrigin
      ? "One of the allowed origins is not a valid origin — see the Embed tab."
      : null;

  async function save() {
    if (!config || blocked || saving) return;
    const list = origins.map((o) => o.trim()).filter(Boolean);
    setSaving(true);
    setSaveError(null);
    setNote(null);
    try {
      let target = id;
      if (isNew) {
        const created = await createAgent(name, config, list);
        target = created.id;
      } else {
        await saveAgent(id, name, config, list);
      }
      // Separate endpoint, and deliberately so: credentials are write-only and never travel
      // with the config the console can read back.
      if (Object.keys(secretDraft).length > 0) {
        setSecrets(await saveSecrets(target, secretDraft));
        setSecretDraft({});
      }
      if (isNew) {
        router.push(`/agents/${target}`);
        return;
      }
      setOrigins(list);
      setSaved(fingerprint({ name, config, origins: list }));
      setNote("Saved. The next call reads these values — no redeploy.");
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  const saveLabel = saving
    ? "Saving…"
    : isNew
      ? "Create agent"
      : !dirty
        ? "No changes"
        : configDirty && secretsDirty
          ? "Save changes and credentials"
          : secretsDirty
            ? "Save credentials"
            : "Save changes";

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-10">
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0 flex-1">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Agent name"
            aria-label="Agent name"
            className="w-full border-0 bg-transparent text-2xl font-semibold text-ink outline-none placeholder:text-faint"
          />
          <div className="mt-1 flex items-center gap-3">
            <span className="font-mono text-xs text-faint">{isNew ? "unsaved" : id}</span>
            {dirty && !isNew && <Badge tone="warn">unsaved changes</Badge>}
          </div>
        </div>
        {!isNew && (
          <div className="flex shrink-0 gap-4 pt-1 text-sm text-muted">
            <Link href={`/agents/${id}/live`} className="hover:text-ink">
              Live
            </Link>
            <Link href={`/agents/${id}/escalations`} className="hover:text-ink">
              Escalations
            </Link>
          </div>
        )}
      </div>

      <div className="mt-6">
        <Tabs tabs={TABS} active={tab} onSelect={setTab} />
      </div>

      <section className="mt-8 pb-8">
        {tab === "Persona" && (
          <PersonaTab
            persona={config.persona}
            onChange={(patch: Partial<Persona>) => patchConfig("persona", patch)}
          />
        )}
        {tab === "Knowledge" && (
          <KnowledgeTab
            knowledge={config.knowledge}
            onChange={(patch: Partial<Knowledge>) => patchConfig("knowledge", patch)}
          />
        )}
        {tab === "Voice" && (
          <VoiceTab
            voice={config.voice}
            onChange={(patch: Partial<Voice>) => patchConfig("voice", patch)}
          />
        )}
        {tab === "Integrations" && (
          <IntegrationsTab
            isNew={isNew}
            secrets={secrets}
            draft={secretDraft}
            onDraft={setSecretField}
            tools={config.tools_enabled}
            onTools={(patch: Partial<ToolsEnabled>) => patchConfig("tools_enabled", patch)}
          />
        )}
        {tab === "Embed" && (
          <EmbedTab id={id} isNew={isNew} origins={origins} onChange={setOrigins} />
        )}
      </section>

      <div className="sticky bottom-0 -mx-6 border-t border-line bg-surface/95 px-6 py-4 backdrop-blur">
        <div className="flex items-center gap-4">
          <Button onClick={save} disabled={saving || Boolean(blocked) || (!isNew && !dirty)}>
            {saveLabel}
          </Button>
          <span className="text-xs text-muted">
            {blocked ??
              note ??
              (dirty
                ? "Not live yet. The running config is whatever was saved last."
                : "In sync with the server.")}
          </span>
        </div>
        {saveError && (
          <p className="mt-2 font-mono text-xs text-escalate">{saveError}</p>
        )}
      </div>
    </main>
  );
}
