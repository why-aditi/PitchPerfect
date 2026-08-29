"use client";

import type { SecretsSet, ToolsEnabled } from "@/lib/types";
import { Badge, Button, Card, Field, Input, Toggle } from "@/components/ui";
import { Group, Hint } from "./bits";

/** Pending secret writes. A key is present only if the operator touched that field. */
export type SecretDraft = Record<string, string | null>;

const TOOLS: {
  key: keyof ToolsEnabled;
  label: string;
  /** What turning it off does to a live call, not what the flag is named. */
  hint: string;
}[] = [
  {
    key: "pricing",
    label: "Pricing lookup",
    hint: "Off: asked what it costs, the agent has no number it is allowed to say and offers to follow up instead.",
  },
  {
    key: "battlecards",
    label: "Competitor battlecards",
    hint: "Off: a competitor question gets an honest no-data answer. The agent will not position against anyone.",
  },
  {
    key: "calendar",
    label: "Cal.com scheduling",
    hint: "Off: no availability and no booking, so the top goal in the hierarchy is unreachable on the call itself.",
  },
  {
    key: "crm",
    label: "HubSpot contact and deal",
    hint: "Off: the lead is still captured on the call record, but nothing is written to the CRM.",
  },
  {
    key: "escalation",
    label: "Escalate to a human",
    hint: "Off: “get me a real person” is answered with a follow-up promise instead of a Slack ping and a rep joining the channel.",
  },
];

/**
 * Write-only, and the UI has to hold that line: the API returns "set" or null and never a
 * value, so there is nothing to prefill with. A field that rendered dots for a stored key
 * could send those dots back as the new key on the next save.
 */
function SecretField({
  label,
  hint,
  placeholder,
  stored,
  draft,
  onDraft,
}: {
  label: string;
  hint: string;
  placeholder: string;
  stored: boolean;
  draft: string | null | undefined;
  onDraft: (v: string | null | undefined) => void;
}) {
  const editing = typeof draft === "string";
  const clearing = draft === null;

  return (
    <div className="space-y-1.5">
      <p className="text-sm text-ink">{label}</p>
      <p className="text-xs leading-relaxed text-faint">{hint}</p>

      {stored && !editing && !clearing && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-line bg-raised px-3 py-2">
          <Badge tone="live">stored</Badge>
          <span className="flex gap-1">
            <Button variant="quiet" className="px-2 py-1 text-xs" onClick={() => onDraft("")}>
              Replace
            </Button>
            <Button variant="quiet" className="px-2 py-1 text-xs" onClick={() => onDraft(null)}>
              Remove
            </Button>
          </span>
        </div>
      )}

      {clearing && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-escalate/40 bg-escalate/5 px-3 py-2">
          <span className="text-xs text-escalate">Will be cleared when you save.</span>
          <Button variant="quiet" className="px-2 py-1 text-xs" onClick={() => onDraft(undefined)}>
            Undo
          </Button>
        </div>
      )}

      {(editing || (!stored && !clearing)) && (
        <div className="space-y-1.5">
          <Input
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={editing ? draft : ""}
            placeholder={placeholder}
            onChange={(e) => onDraft(e.target.value === "" ? undefined : e.target.value)}
            className="font-mono"
          />
          {editing && (
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs text-thinking">
                {stored ? "Replaces the stored value on save." : "Saved when you save the agent."}
              </span>
              <Button
                variant="quiet"
                className="px-2 py-1 text-xs"
                onClick={() => onDraft(undefined)}
              >
                Cancel
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function IntegrationsTab({
  isNew,
  secrets,
  draft,
  onDraft,
  tools,
  onTools,
}: {
  isNew: boolean;
  secrets: SecretsSet | null;
  draft: SecretDraft;
  onDraft: (key: string, value: string | null | undefined) => void;
  tools: ToolsEnabled;
  onTools: (patch: Partial<ToolsEnabled>) => void;
}) {
  // Non-secret companions read back as themselves, so they behave like ordinary inputs —
  // they just travel on the same write-only endpoint as the credentials beside them.
  const plain = (key: keyof SecretsSet, fallback = "") => {
    const drafted = draft[key];
    if (typeof drafted === "string") return drafted;
    const stored = secrets?.[key];
    return typeof stored === "string" && stored !== "set" ? stored : fallback;
  };

  const stored = (key: keyof SecretsSet) => secrets?.[key] === "set";

  return (
    <div className="space-y-10">
      <Group title="Credentials">
        <Hint>
          Written only. The API reads these back as &ldquo;stored&rdquo; and never as the value,
          so a key you paste here cannot be recovered from this screen — keep it wherever you got
          it from.
          {isNew && " They are saved the moment the agent is created."}
        </Hint>

        <Card className="space-y-5 p-4">
          <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-faint">Cal.com</p>
          <SecretField
            label="API key"
            hint="Reads availability and creates the booking when a demo is agreed."
            placeholder="cal_live_…"
            stored={stored("calcom_api_key")}
            draft={draft.calcom_api_key}
            onDraft={(v) => onDraft("calcom_api_key", v)}
          />
          <Field
            label="Event type id"
            hint="Which of your Cal.com event types the demo is booked against."
          >
            <Input
              value={plain("calcom_event_type_id")}
              onChange={(e) => onDraft("calcom_event_type_id", e.target.value)}
              placeholder="1234567"
              className="font-mono"
            />
          </Field>
        </Card>

        <Card className="space-y-5 p-4">
          <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-faint">HubSpot</p>
          <SecretField
            label="Private app token"
            hint="Creates the contact and the deal. Needs the crm.objects scopes."
            placeholder="pat-…"
            stored={stored("hubspot_token")}
            draft={draft.hubspot_token}
            onDraft={(v) => onDraft("hubspot_token", v)}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Pipeline">
              <Input
                value={plain("hubspot_pipeline", "default")}
                onChange={(e) => onDraft("hubspot_pipeline", e.target.value)}
                className="font-mono"
              />
            </Field>
            <Field label="Deal stage">
              <Input
                value={plain("hubspot_deal_stage", "appointmentscheduled")}
                onChange={(e) => onDraft("hubspot_deal_stage", e.target.value)}
                className="font-mono"
              />
            </Field>
          </div>
        </Card>

        <Card className="space-y-5 p-4">
          <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-faint">Slack</p>
          <SecretField
            label="Incoming webhook URL"
            hint="Where an escalation lands, with the lead summary, while the prospect is still on the call."
            placeholder="https://hooks.slack.com/services/…"
            stored={stored("slack_webhook_url")}
            draft={draft.slack_webhook_url}
            onDraft={(v) => onDraft("slack_webhook_url", v)}
          />
        </Card>
      </Group>

      <Group title="Tools">
        <Hint>
          A disabled tool is left out of the specs sent to the model, so it cannot be called and
          then refused — the agent simply never offers it.
        </Hint>
        <div className="space-y-2">
          {TOOLS.map((t) => (
            <Toggle
              key={t.key}
              checked={tools[t.key]}
              onChange={(v) => onTools({ [t.key]: v } as Partial<ToolsEnabled>)}
              label={t.label}
              hint={t.hint}
            />
          ))}
        </div>
        {tools.calendar && !stored("calcom_api_key") && !draft.calcom_api_key && (
          <Hint>
            Scheduling is on with no Cal.com key stored. The tool will error on the call and the
            agent will fall back to a follow-up.
          </Hint>
        )}
        {tools.escalation && !stored("slack_webhook_url") && !draft.slack_webhook_url && (
          <Hint>
            Escalation is on with no Slack webhook stored. Nobody will be paged when the agent
            hands off.
          </Hint>
        )}
      </Group>
    </div>
  );
}
