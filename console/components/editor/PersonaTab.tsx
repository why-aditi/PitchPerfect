"use client";

import type { Persona } from "@/lib/types";
import { Card, Field, Input, Textarea } from "@/components/ui";
import { Group, Hint, ListEditor } from "./bits";

const OBJECTIONS = ["pricing", "trust", "product", "competitor"] as const;

const OBJECTION_HINT: Record<(typeof OBJECTIONS)[number], string> = {
  pricing: "Spoken when the prospect pushes back on cost.",
  trust: "Spoken when the prospect doubts the company, not the product.",
  product: "Spoken when a capability is questioned. Answers still come from tool data only.",
  competitor: "Spoken after get_battlecard returns, never before it.",
};

export function PersonaTab({
  persona,
  onChange,
}: {
  persona: Persona;
  onChange: (patch: Partial<Persona>) => void;
}) {
  return (
    <div className="space-y-8">
      <Group title="Who the agent is">
        <div className="space-y-4">
          <Field
            label="Identity"
            hint="One paragraph. Everything the agent says about itself is built from this."
          >
            <Textarea
              rows={4}
              value={persona.identity}
              onChange={(e) => onChange({ identity: e.target.value })}
              placeholder="Sells Vantage, a work management platform for mid-market operations teams."
            />
          </Field>
          <Field
            label="Greeting"
            hint="Spoken by the engine before the model sees a turn. It carries the AI disclosure — keep it."
          >
            <Textarea
              rows={3}
              value={persona.greeting}
              onChange={(e) => onChange({ greeting: e.target.value })}
            />
          </Field>
        </div>
      </Group>

      <Group title="Goal hierarchy">
        <Hint>
          Read top to bottom. The agent pursues the highest goal still available, so the order
          decides whether a lukewarm call ends in a demo or a follow-up.
        </Hint>
        <ListEditor
          ordered
          items={persona.goal_hierarchy}
          onChange={(goal_hierarchy) => onChange({ goal_hierarchy })}
          placeholder="book a demo"
          addLabel="Add goal"
          emptyNote="No goals. The agent will converse without ever steering the call."
        />
      </Group>

      <Group title="Objection strategies">
        <div className="space-y-4">
          {OBJECTIONS.map((k) => (
            <Field key={k} label={<span className="capitalize">{k}</span>} hint={OBJECTION_HINT[k]}>
              <Textarea
                rows={2}
                value={persona.objection_strategies[k] ?? ""}
                onChange={(e) =>
                  onChange({
                    objection_strategies: {
                      ...persona.objection_strategies,
                      [k]: e.target.value,
                    },
                  })
                }
              />
            </Field>
          ))}
        </div>
      </Group>

      <Group title="Escalation">
        <div className="space-y-4">
          <div>
            <p className="mb-2 text-sm text-ink">Triggers</p>
            <Hint>
              Conditions that hand the call to a human. Each one is a phrase the model matches
              against the conversation, so write them the way a prospect would sound.
            </Hint>
            <div className="mt-2">
              <ListEditor
                items={persona.escalation_triggers}
                onChange={(escalation_triggers) => onChange({ escalation_triggers })}
                placeholder="asks for a human"
                addLabel="Add trigger"
                emptyNote="No triggers. Only the seat threshold below can escalate a call."
              />
            </div>
          </div>

          <Field
            label="Seat threshold"
            hint="A deal above this many seats escalates. A number, deliberately, so the model is not the one deciding what counts as big."
          >
            <Input
              type="number"
              min={0}
              value={persona.escalation_seat_threshold}
              onChange={(e) =>
                onChange({ escalation_seat_threshold: Number(e.target.value) || 0 })
              }
            />
          </Field>
        </div>
      </Group>

      <Card className="p-4">
        <p className="mb-2 font-mono text-[11px] uppercase tracking-[0.14em] text-faint">
          Not editable
        </p>
        <ul className="space-y-1.5 text-xs leading-relaxed text-muted">
          <li>Never invent a price, feature, date or customer name — those come from tools.</li>
          <li>If a tool returns no data, say so. Never estimate.</li>
          <li>Two or three sentences per turn. One question at a time.</li>
          <li>If interrupted, drop the previous point entirely; never resume it verbatim.</li>
          <li>Call update_lead_state on learning something, before replying.</li>
        </ul>
        <p className="mt-3 text-xs leading-relaxed text-faint">
          These are the guarantees the product makes, so the console cannot weaken them.
        </p>
      </Card>
    </div>
  );
}
