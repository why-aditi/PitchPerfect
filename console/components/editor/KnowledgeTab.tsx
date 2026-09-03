"use client";

import { useState } from "react";
import { importTiers } from "@/lib/api";
import type { Battlecard, Knowledge, Tier } from "@/lib/types";
import { Badge, Button, Card, Field, Input, Textarea, Toggle } from "@/components/ui";
import {
  ErrorNote,
  Group,
  Hint,
  IconButton,
  IconDuplicate,
  IconPlus,
  IconTrash,
  ListEditor,
  RawJson,
  Warn,
} from "./bits";

/* ---------------------------------------------------------------- validation */

const isObj = (u: unknown): u is Record<string, unknown> =>
  typeof u === "object" && u !== null && !Array.isArray(u);

const isStrings = (u: unknown): u is string[] =>
  Array.isArray(u) && u.every((s) => typeof s === "string");

/**
 * The raw-JSON hatch is the one place a shape the runtime cannot read could get into the
 * config, so it is checked field by field against models.py rather than cast. Anything
 * rejected here never reaches state.
 */
function parseTiers(u: unknown): { tiers: Tier[] } | { error: string } {
  if (!Array.isArray(u)) return { error: "Expected an array of tiers." };
  const tiers: Tier[] = [];
  for (let i = 0; i < u.length; i++) {
    const t = u[i];
    const at = `Tier ${i + 1}`;
    if (!isObj(t)) return { error: `${at}: expected an object.` };
    if (typeof t.name !== "string") return { error: `${at}: "name" must be a string.` };
    if (typeof t.per_seat_month !== "number")
      return { error: `${at}: "per_seat_month" must be a number.` };
    if (typeof t.min_seats !== "number") return { error: `${at}: "min_seats" must be a number.` };
    if (t.max_seats !== null && typeof t.max_seats !== "number")
      return { error: `${at}: "max_seats" must be a number or null.` };
    if (t.volume_break !== null && t.volume_break !== undefined) {
      const vb = t.volume_break;
      if (!isObj(vb) || typeof vb.seats !== "number" || typeof vb.per_seat_month !== "number")
        return { error: `${at}: "volume_break" must be null or { seats, per_seat_month }.` };
    }
    if (t.features !== undefined && !isStrings(t.features))
      return { error: `${at}: "features" must be an array of strings.` };
    tiers.push({
      name: t.name,
      per_seat_month: t.per_seat_month,
      min_seats: t.min_seats,
      max_seats: (t.max_seats as number | null) ?? null,
      volume_break: (t.volume_break as Tier["volume_break"]) ?? null,
      features: (t.features as string[] | undefined) ?? [],
    });
  }
  return { tiers };
}

function parseBattlecards(
  u: unknown,
): { cards: Record<string, Battlecard> } | { error: string } {
  if (!isObj(u)) return { error: "Expected an object keyed by competitor." };
  const cards: Record<string, Battlecard> = {};
  for (const [key, raw] of Object.entries(u)) {
    if (!key.trim()) return { error: "A competitor key cannot be empty." };
    if (!isObj(raw)) return { error: `"${key}": expected an object.` };
    if (typeof raw.positioning !== "string")
      return { error: `"${key}": "positioning" must be a string.` };
    if (raw.we_win !== undefined && !isStrings(raw.we_win))
      return { error: `"${key}": "we_win" must be an array of strings.` };
    if (raw.we_concede !== undefined && !isStrings(raw.we_concede))
      return { error: `"${key}": "we_concede" must be an array of strings.` };
    if (raw.proof_point !== undefined && typeof raw.proof_point !== "string")
      return { error: `"${key}": "proof_point" must be a string.` };
    cards[key] = {
      positioning: raw.positioning,
      we_win: (raw.we_win as string[] | undefined) ?? [],
      we_concede: (raw.we_concede as string[] | undefined) ?? [],
      proof_point: (raw.proof_point as string | undefined) ?? "",
    };
  }
  return { cards };
}

/**
 * get_pricing looks a tier up by seat count, so a gap means the agent has no answer for a
 * real prospect and an overlap means two answers. Either is a bug to see before a call
 * rather than during one — hence a warning on the tab, not a blocked save.
 */
function coverageWarnings(tiers: Tier[]): string[] {
  const out: string[] = [];
  const named = tiers.map((t, i) => ({ ...t, label: t.name.trim() || `tier ${i + 1}` }));

  for (const t of named) {
    if (t.max_seats !== null && t.max_seats < t.min_seats)
      out.push(`${t.label} ends at ${t.max_seats} seats but starts at ${t.min_seats}.`);
    if (t.volume_break && t.max_seats !== null && t.volume_break.seats > t.max_seats)
      out.push(
        `${t.label}'s volume break needs ${t.volume_break.seats} seats, more than the ${t.max_seats} the tier allows — it can never apply.`,
      );
  }

  const sorted = [...named].sort((a, b) => a.min_seats - b.min_seats);
  for (let i = 0; i < sorted.length - 1; i++) {
    const cur = sorted[i];
    const next = sorted[i + 1];
    if (cur.max_seats === null) {
      out.push(`${cur.label} has no upper limit, so it swallows every tier above it.`);
      break;
    }
    if (next.min_seats <= cur.max_seats)
      out.push(
        `${cur.label} and ${next.label} both cover ${next.min_seats}–${Math.min(cur.max_seats, next.max_seats ?? cur.max_seats)} seats.`,
      );
    else if (next.min_seats > cur.max_seats + 1)
      out.push(
        `Nothing covers ${cur.max_seats + 1}–${next.min_seats - 1} seats, between ${cur.label} and ${next.label}.`,
      );
  }

  const last = sorted[sorted.length - 1];
  if (last && last.max_seats !== null)
    out.push(`Nothing covers more than ${last.max_seats} seats. Give the top tier no upper limit.`);
  const first = sorted[0];
  if (first && first.min_seats > 1)
    out.push(`Nothing covers 1–${first.min_seats - 1} seats.`);

  return out;
}

const BLANK_TIER: Tier = {
  name: "",
  per_seat_month: 0,
  min_seats: 1,
  max_seats: null,
  volume_break: null,
  features: [],
};

const BLANK_CARD: Battlecard = { positioning: "", we_win: [], we_concede: [], proof_point: "" };

/* ---------------------------------------------------------------- tiers */

function TierCard({
  tier,
  currency,
  onChange,
  onDuplicate,
  onRemove,
}: {
  tier: Tier;
  currency: string;
  onChange: (next: Tier) => void;
  onDuplicate: () => void;
  onRemove: () => void;
}) {
  const patch = (p: Partial<Tier>) => onChange({ ...tier, ...p });

  return (
    <Card className="space-y-4 p-4">
      <div className="flex items-center gap-2">
        <Input
          value={tier.name}
          placeholder="Tier name"
          onChange={(e) => patch({ name: e.target.value })}
          className="font-medium"
        />
        <IconButton label="Duplicate tier" onClick={onDuplicate}>
          <IconDuplicate />
        </IconButton>
        <IconButton label="Remove tier" tone="danger" onClick={onRemove}>
          <IconTrash />
        </IconButton>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Field label={`Per seat / month (${currency})`}>
          <Input
            type="number"
            min={0}
            step="0.01"
            value={tier.per_seat_month}
            onChange={(e) => patch({ per_seat_month: Number(e.target.value) || 0 })}
          />
        </Field>
        <Field label="From seats">
          <Input
            type="number"
            min={0}
            value={tier.min_seats}
            onChange={(e) => patch({ min_seats: Number(e.target.value) || 0 })}
          />
        </Field>
        {/* Not a <Field>: a bare button inside a label is ambiguous to click. */}
        <div>
          <span className="text-sm text-ink">To seats</span>
          <div className="mt-1.5">
          {tier.max_seats === null ? (
            <button
              type="button"
              onClick={() => patch({ max_seats: Math.max(tier.min_seats, 1) })}
              className="w-full rounded-lg border border-dashed border-line bg-raised px-3 py-2 text-left text-sm text-faint transition-colors hover:border-brand/50 hover:text-ink"
            >
              No upper limit
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <Input
                type="number"
                min={0}
                value={tier.max_seats}
                onChange={(e) => patch({ max_seats: Number(e.target.value) || 0 })}
              />
              <Button
                variant="quiet"
                className="shrink-0 px-2 py-1 text-xs"
                onClick={() => patch({ max_seats: null })}
              >
                No limit
              </Button>
            </div>
          )}
          </div>
        </div>
      </div>

      <div className="space-y-3">
        <Toggle
          checked={tier.volume_break !== null}
          onChange={(on) =>
            patch({
              volume_break: on
                ? { seats: Math.max(tier.min_seats * 2, 10), per_seat_month: tier.per_seat_month }
                : null,
            })
          }
          label="Volume break"
          hint="A second price the agent may quote once the seat count is high enough."
        />
        {tier.volume_break && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="At seats">
              <Input
                type="number"
                min={0}
                value={tier.volume_break.seats}
                onChange={(e) =>
                  patch({
                    volume_break: {
                      seats: Number(e.target.value) || 0,
                      per_seat_month: tier.volume_break!.per_seat_month,
                    },
                  })
                }
              />
            </Field>
            <Field label={`Per seat / month (${currency})`}>
              <Input
                type="number"
                min={0}
                step="0.01"
                value={tier.volume_break.per_seat_month}
                onChange={(e) =>
                  patch({
                    volume_break: {
                      seats: tier.volume_break!.seats,
                      per_seat_month: Number(e.target.value) || 0,
                    },
                  })
                }
              />
            </Field>
          </div>
        )}
      </div>

      <div>
        <p className="mb-2 text-sm text-ink">Included features</p>
        <ListEditor
          items={tier.features}
          onChange={(features) => patch({ features })}
          placeholder="Unlimited projects"
          addLabel="Add feature"
          emptyNote="No features listed. Asked what this tier includes, the agent has nothing to read out."
        />
      </div>
    </Card>
  );
}

/* ---------------------------------------------------------------- battlecards */

function BattlecardCard({
  slug,
  card,
  onChange,
  onRename,
  onRemove,
}: {
  slug: string;
  card: Battlecard;
  onChange: (next: Battlecard) => void;
  onRename: (next: string) => string | null;
  onRemove: () => void;
}) {
  // The key is edited as a draft and committed on blur: rewriting the record on every
  // keystroke would collide with itself halfway through a rename.
  const [draft, setDraft] = useState(slug);
  const [error, setError] = useState<string | null>(null);
  const patch = (p: Partial<Battlecard>) => onChange({ ...card, ...p });

  const commit = () => {
    if (draft === slug) return;
    const rejected = onRename(draft);
    setError(rejected);
    if (rejected) setDraft(slug);
  };

  return (
    <Card className="space-y-4 p-4">
      <div className="flex items-center gap-2">
        <Input
          value={draft}
          placeholder="competitor-slug"
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
          className="font-mono"
        />
        <IconButton label="Remove competitor" tone="danger" onClick={onRemove}>
          <IconTrash />
        </IconButton>
      </div>
      {error && <ErrorNote>{error}</ErrorNote>}

      <Field
        label="Positioning"
        hint="How we sit against them in one or two sentences. Spoken close to verbatim."
      >
        <Textarea
          rows={3}
          value={card.positioning}
          onChange={(e) => patch({ positioning: e.target.value })}
        />
      </Field>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <p className="mb-2 text-sm text-ink">Where we win</p>
          <ListEditor
            items={card.we_win}
            onChange={(we_win) => patch({ we_win })}
            placeholder="Faster to roll out"
            addLabel="Add point"
          />
        </div>
        <div>
          <p className="mb-2 text-sm text-ink">Where we concede</p>
          <ListEditor
            items={card.we_concede}
            onChange={(we_concede) => patch({ we_concede })}
            placeholder="Fewer native integrations"
            addLabel="Add point"
          />
        </div>
      </div>
      <Hint>
        The agent acknowledges one genuine strength before positioning, so an empty concede
        list makes it sound evasive.
      </Hint>

      <Field label="Proof point" hint="One verifiable fact. The agent may not invent another.">
        <Input
          value={card.proof_point}
          onChange={(e) => patch({ proof_point: e.target.value })}
          placeholder="Northwind moved 400 seats over in six weeks."
        />
      </Field>
    </Card>
  );
}

/* ---------------------------------------------------------------- tab */

/**
 * Pulls the tiers out of the agent's Notion pricing database into the editor, unsaved.
 *
 * It replaces rather than merges, because a name is the only thing a Notion row and a
 * tier here share and matching on it would silently keep a tier the operator deleted in
 * Notion. Replacing is the honest import; the review step before saving is this being
 * left dirty rather than written.
 */
function ImportFromNotion({ id, onTiers }: { id: string; onTiers: (t: Tier[]) => void }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setNote(null);
    setError(null);
    try {
      const r = await importTiers(id);
      onTiers(r.tiers);
      setNote(
        `${r.tiers.length} tier(s) loaded. ${r.note ?? ""} Nothing is saved until you save the agent.`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      <Button variant="ghost" className="px-3 py-1.5 text-xs" onClick={run} disabled={busy}>
        {busy ? "Reading Notion…" : "Import from Notion"}
      </Button>
      {note && <Hint>{note}</Hint>}
      {error && <ErrorNote>{error}</ErrorNote>}
    </div>
  );
}

export function KnowledgeTab({
  id,
  isNew,
  knowledge,
  onChange,
}: {
  id: string;
  isNew: boolean;
  knowledge: Knowledge;
  onChange: (patch: Partial<Knowledge>) => void;
}) {
  const { tiers, battlecards, currency } = knowledge;
  const warnings = coverageWarnings(tiers);
  const entries = Object.entries(battlecards);

  const setTier = (i: number, next: Tier) =>
    onChange({ tiers: tiers.map((t, n) => (n === i ? next : t)) });

  const renameCard = (from: string, to: string): string | null => {
    const key = to.trim();
    if (!key) return "A competitor needs a key.";
    if (key !== from && key in battlecards) return `"${key}" already has a battlecard.`;
    // Rebuilt in place so the card does not jump to the end of the list on rename.
    onChange({
      battlecards: Object.fromEntries(
        entries.map(([k, v]) => (k === from ? [key, v] : [k, v])),
      ),
    });
    return null;
  };

  return (
    <div className="space-y-10">
      <Hint>
        The only prices and competitor claims this agent may speak. Everything here reaches the
        prospect through a tool call, never through the model&apos;s memory — so an empty section
        is an honest &ldquo;I don&apos;t have that&rdquo; on the call, not an improvisation.
      </Hint>

      <Group
        title="Pricing tiers"
        action={
          <div className="flex items-center gap-2">
            <Input
              value={currency}
              onChange={(e) => onChange({ currency: e.target.value })}
              aria-label="Currency"
              className="w-20 text-center font-mono text-xs uppercase"
            />
            <Button
              variant="ghost"
              className="px-3 py-1.5 text-xs"
              onClick={() => onChange({ tiers: [...tiers, { ...BLANK_TIER }] })}
            >
              <IconPlus />
              Add tier
            </Button>
          </div>
        }
      >
        {warnings.length > 0 && (
          <div className="space-y-2">
            {warnings.map((w) => (
              <Warn key={w}>{w}</Warn>
            ))}
          </div>
        )}

        {tiers.length === 0 ? (
          <p className="rounded-xl border border-dashed border-line px-6 py-8 text-center text-sm text-muted">
            No pricing table. get_pricing will return nothing and the agent will offer a follow-up
            instead of a number.
          </p>
        ) : (
          <div className="space-y-3">
            {tiers.map((tier, i) => (
              <TierCard
                key={i}
                tier={tier}
                currency={currency}
                onChange={(next) => setTier(i, next)}
                onDuplicate={() =>
                  onChange({
                    tiers: [
                      ...tiers.slice(0, i + 1),
                      { ...tier, name: `${tier.name} copy`, features: [...tier.features] },
                      ...tiers.slice(i + 1),
                    ],
                  })
                }
                onRemove={() => onChange({ tiers: tiers.filter((_, n) => n !== i) })}
              />
            ))}
          </div>
        )}

        {/* Needs stored secrets to read, and a new agent has none until it is saved once. */}
        {!isNew && <ImportFromNotion id={id} onTiers={(t) => onChange({ tiers: t })} />}

        <RawJson
          label="Raw JSON — tiers"
          value={tiers}
          onApply={(parsed) => {
            const r = parseTiers(parsed);
            if ("error" in r) return r.error;
            onChange({ tiers: r.tiers });
            return null;
          }}
        />
      </Group>

      <Group
        title="Battlecards"
        action={
          <Button
            variant="ghost"
            className="px-3 py-1.5 text-xs"
            onClick={() => {
              let key = "competitor";
              for (let n = 2; key in battlecards; n++) key = `competitor-${n}`;
              onChange({ battlecards: { ...battlecards, [key]: { ...BLANK_CARD } } });
            }}
          >
            <IconPlus />
            Add competitor
          </Button>
        }
      >
        <Hint>
          Keyed by the name a prospect would say, lowercased. get_battlecard looks the key up
          directly; a competitor with no card gets an explicit no-data answer.
        </Hint>

        {entries.length === 0 ? (
          <p className="rounded-xl border border-dashed border-line px-6 py-8 text-center text-sm text-muted">
            No battlecards. Every competitor question will be answered with &ldquo;I don&apos;t
            have that&rdquo;.
          </p>
        ) : (
          <div className="space-y-3">
            {entries.map(([slug, card]) => (
              <BattlecardCard
                key={slug}
                slug={slug}
                card={card}
                onChange={(next) => onChange({ battlecards: { ...battlecards, [slug]: next } })}
                onRename={(to) => renameCard(slug, to)}
                onRemove={() =>
                  onChange({
                    battlecards: Object.fromEntries(entries.filter(([k]) => k !== slug)),
                  })
                }
              />
            ))}
          </div>
        )}

        {entries.length > 0 && (
          <div>
            <Badge>
              {entries.length} {entries.length === 1 ? "competitor" : "competitors"}
            </Badge>
          </div>
        )}

        <RawJson
          label="Raw JSON — battlecards"
          value={battlecards}
          onApply={(parsed) => {
            const r = parseBattlecards(parsed);
            if ("error" in r) return r.error;
            onChange({ battlecards: r.cards });
            return null;
          }}
          rows={16}
        />
      </Group>
    </div>
  );
}
