"use client";

import { use, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createAgent, getAgent, saveAgent, saveSecrets } from "@/lib/api";
import type { AgentConfig, Knowledge, Persona, SecretsSet, ToolsEnabled, Voice } from "@/lib/types";
import { Badge, Button, cx } from "@/components/ui";
import { useSection } from "@/components/Shell";
import { EmbedTab, originError } from "@/components/editor/EmbedTab";
import { IntegrationsTab, type SecretDraft } from "@/components/editor/IntegrationsTab";
import { KnowledgeTab } from "@/components/editor/KnowledgeTab";
import { PersonaTab } from "@/components/editor/PersonaTab";
import { VoiceTab } from "@/components/editor/VoiceTab";

/** A new agent starts from the same defaults models.py would have given it. */
const BLANK: AgentConfig = {
  persona: {
    identity: "",
    greeting:
      "Hi, you're speaking with an AI sales assistant. This call is transcribed. What can I help you with?",
    goal_hierarchy: ["book a demo", "qualify with BANT", "create a follow-up", "escalate to a human"],
    objection_strategies: {
      // Byte-identical to DEFAULT_STRATEGIES["pricing"] in backend/models.py, where the
      // reasoning for the wording lives. Both are starting points an operator then edits,
      // so they only have to agree at the moment an agent is created — but when they
      // disagree, a console-made agent and a seeded one negotiate differently and nothing
      // reports it.
      pricing:
        "Anchor on per-seat value before any total. Probe the real budget and the real blocker — it is usually the annual number, not the rate. Concede only in trades, never in gifts: name what you need back before you give anything, and give one thing at a time. If they push a third time, hold the line and offer a human rather than a better price. Never discount unprompted.",
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
  // A new agent starts with an empty ladder on purpose: nothing has been authorised yet,
  // so it can hold a price but has nothing to trade until an operator fills the tab in.
  knowledge: { currency: "USD", tiers: [], battlecards: {}, concessions: [] },
  tools_enabled: {
    pricing: true,
    battlecards: true,
    calendar: true,
    crm: true,
    escalation: true,
    negotiation: true,
  },
  llm_model: "openai/gpt-oss-20b",
};

/** What "unsaved" is measured against: the shape the server last confirmed. */
type Snapshot = { name: string; config: AgentConfig; origins: string[] };
const fingerprint = (s: Snapshot) => JSON.stringify(s);

export default function AgentEditor({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const isNew = id === "new";
  const router = useRouter();

  const tab = useSection();
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

  // Ctrl/Cmd+S is what every operator will try first. The browser's own save dialog is
  // never what they meant.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        document.getElementById("save-agent")?.click();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
      ? "One of the allowed origins is not a valid origin — see the Embed section."
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

  const status =
    blocked ??
    note ??
    (dirty ? "Not live yet. The running config is whatever was saved last." : "In sync with the server.");

  return (
    <>
      <div className="sticky top-0 z-10 flex min-h-16 flex-wrap items-center justify-between gap-3 border-b border-line bg-surface/80 px-6 py-3 backdrop-blur lg:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={isNew ? "Name your agent" : "Agent name"}
            aria-label="Agent name"
            autoFocus={isNew}
            className={cx(
              "min-w-0 bg-transparent font-display text-xl font-semibold tracking-tight text-ink outline-none placeholder:text-faint",
              isNew ? "w-72 rounded-lg border border-dashed border-line px-3 py-1 focus:border-brand" : "w-64 border-0",
            )}
          />
          {!isNew && <span className="hidden rounded-md bg-raised px-2 py-0.5 font-mono text-xs text-muted sm:inline">{id}</span>}
          {dirty && !isNew && <Badge tone="warn">Unsaved changes</Badge>}
        </div>
        <div className="flex items-center gap-2">
          {dirty && !isNew && (
            <Button variant="ghost" className="px-3 py-1.5 text-xs" onClick={() => window.location.reload()}>
              Discard
            </Button>
          )}
          <Button id="save-agent" onClick={save} disabled={saving || Boolean(blocked) || (!isNew && !dirty)} className="px-3 py-1.5 text-xs">
            {saveLabel}
          </Button>
        </div>
      </div>

      <div className="mx-auto w-full max-w-3xl px-6 py-8 lg:px-8">
        <h1 className="font-display text-2xl font-semibold text-ink">{tab}</h1>
        <p className="mt-1 text-sm text-muted">{TAB_INTRO[tab]}</p>
        <p
          className={cx(
            "mt-3 text-xs leading-relaxed",
            saveError ? "font-mono text-escalate" : blocked || dirty ? "text-thinking" : "text-faint",
          )}
        >
          {saveError ?? status} {!isNew && <span className="text-faint">· Ctrl+S saves</span>}
        </p>

        <section className="mt-8 pb-16">
          {tab === "Persona" && (
            <PersonaTab
              persona={config.persona}
              onChange={(patch: Partial<Persona>) => patchConfig("persona", patch)}
            />
          )}
          {tab === "Knowledge" && (
            <KnowledgeTab
              id={id}
              isNew={isNew}
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
      </div>
    </>
  );
}

const TAB_INTRO: Record<ReturnType<typeof useSection>, string> = {
  Persona: "Who the agent is and what it is trying to do on the call.",
  Knowledge: "The only prices and competitor claims it may speak.",
  Voice: "How it decides when you have started and stopped talking.",
  Integrations: "Where it writes when a call goes well, and which tools it may call.",
  Embed: "The script tag, and the sites allowed to start a call.",
};
