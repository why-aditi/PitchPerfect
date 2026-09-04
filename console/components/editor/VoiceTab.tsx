"use client";

import type { Voice } from "@/lib/types";
import { Button, Field, Input, Slider, Toggle } from "@/components/ui";
import { Group, Hint, JsonField, ListEditor } from "./bits";

/**
 * The Voice() defaults in models.py. Anything that differs from these is a deliberate
 * choice by the operator, and the tab says so — so this list has to track models.py, not
 * the PRD. silence_duration_ms and max_wait_ms have both moved off the PRD 12
 * reference after a live call where the agent talked over the prospect; leaving the old
 * numbers here would badge every new agent CHANGED against a default it never had.
 */
/**
 * What this tab can reset, and nothing else. Every value tracks models.py — checked
 * against it, not copied once and left to drift.
 *
 * Two bugs lived in the old shape of this constant, and both were live-call failures.
 *
 * It carried `tts_vendor: ""` and `tts_params: {}`, and the reset button spread the whole
 * object — so one click wrote an empty vendor over the agent's voice. models.py types
 * tts_vendor as a plain str, so "" validates and saves, and agora.py then sends
 * `tts: {vendor: ""}` and the engine refuses the join. The next call after that click
 * would simply not start. TTS is not a turn-detection knob and is not edited on this tab,
 * so it has no business in a turn-detection reset.
 *
 * And the numbers had drifted from models.py on five of them, which made a stock agent
 * render "Reset tab to defaults (5 changed)" — an invitation to click. Restoring those
 * numbers would have undone the tuning models.py:76-79 records as having cut turns off
 * "twenty times in thirty".
 */
export const DEFAULTS: Pick<
  Voice,
  | "speech_threshold"
  | "interrupt_duration_ms"
  | "speaking_interrupt_duration_ms"
  | "prefix_padding_ms"
  | "silence_duration_ms"
  | "max_wait_ms"
  | "interruption_enabled"
  | "filler_phrases"
> = {
  speech_threshold: 0.6,
  interrupt_duration_ms: 300,
  speaking_interrupt_duration_ms: 500,
  prefix_padding_ms: 800,
  silence_duration_ms: 550,
  max_wait_ms: 3000,
  interruption_enabled: true,
  filler_phrases: ["Right.", "Let me look.", "Sure."],
};

type NumericKey =
  | "speech_threshold"
  | "interrupt_duration_ms"
  | "speaking_interrupt_duration_ms"
  | "prefix_padding_ms"
  | "silence_duration_ms"
  | "max_wait_ms";

type Knob = {
  key: NumericKey;
  label: string;
  min: number;
  max: number;
  step: number;
  unit?: string;
  /** What a listener would hear change. Every claim here traces to PRD 12. */
  hint: string;
};

const START_OF_SPEECH: Knob[] = [
  {
    key: "speech_threshold",
    label: "Speech threshold",
    min: 0,
    max: 1,
    step: 0.05,
    hint: "How loud a sound has to be before it counts as speech at all. Lower it for a quiet room; too low and a keyboard or a passing voice starts a turn.",
  },
  {
    key: "interrupt_duration_ms",
    label: "Start-of-speech duration",
    min: 0,
    max: 1000,
    step: 20,
    unit: "ms",
    hint: "How long you have to be speaking before the engine decides your turn has started. Keep it low so the agent begins listening the moment you open your mouth.",
  },
  {
    key: "speaking_interrupt_duration_ms",
    label: "Interrupt-while-speaking duration",
    min: 0,
    max: 1500,
    step: 20,
    unit: "ms",
    hint: "How long you have to keep talking to actually cut the agent off mid-sentence. Raise it if a “mm-hmm” stops the agent; leave the field above low so it still starts listening quickly.",
  },
  {
    key: "prefix_padding_ms",
    label: "Prefix padding",
    min: 0,
    max: 2000,
    step: 50,
    unit: "ms",
    hint: "Audio kept from just before speech was detected, so the first word of your sentence is not clipped off what the agent hears.",
  },
];

const END_OF_SPEECH: Knob[] = [
  {
    key: "silence_duration_ms",
    label: "Silence duration",
    min: 100,
    max: 2000,
    step: 20,
    unit: "ms",
    hint: "Quiet after you stop before the agent takes its turn. Shorter feels snappy; too short and it answers a sentence you were only pausing in the middle of.",
  },
  {
    key: "max_wait_ms",
    label: "Max wait",
    min: 500,
    max: 10000,
    step: 100,
    unit: "ms",
    hint: "The hard cap on waiting for you to finish. The agent replies after this even when end-of-turn is still ambiguous, so it can never sit in silence.",
  },
];

function Tunable({
  knob,
  value,
  onChange,
}: {
  knob: Knob;
  value: number;
  onChange: (v: number) => void;
}) {
  const fallback = DEFAULTS[knob.key];
  const isDefault = value === fallback;
  return (
    <div className="space-y-1">
      <Slider
        label={knob.label}
        hint={knob.hint}
        value={value}
        onChange={onChange}
        min={knob.min}
        max={knob.max}
        step={knob.step}
        unit={knob.unit}
        isDefault={isDefault}
      />
      {!isDefault && (
        <div className="flex justify-end">
          <Button
            variant="quiet"
            className="px-2 py-0.5 text-xs"
            onClick={() => onChange(fallback)}
          >
            Reset to {fallback}
            {knob.unit ? ` ${knob.unit}` : ""}
          </Button>
        </div>
      )}
    </div>
  );
}

export function VoiceTab({
  voice,
  onChange,
}: {
  voice: Voice;
  onChange: (patch: Partial<Voice>) => void;
}) {
  const changed = (Object.keys(DEFAULTS) as (keyof typeof DEFAULTS)[]).filter(
    (k) => JSON.stringify(voice[k]) !== JSON.stringify(DEFAULTS[k]),
  );

  return (
    <div className="space-y-10">
      <Group
        title="Turn detection"
        action={
          changed.length > 0 && (
            <Button
              variant="ghost"
              className="px-3 py-1.5 text-xs"
              onClick={() => onChange({ ...DEFAULTS })}
            >
              Reset tab to defaults ({changed.length} changed)
            </Button>
          )
        }
      >
        <Hint>
          Start of speech runs on VAD, end of speech on the semantic detector. These are the two
          halves of how the call feels: the first decides how fast the agent yields, the second
          how long it waits before answering.
        </Hint>
        <div className="space-y-3">
          {START_OF_SPEECH.map((knob) => (
            <Tunable
              key={knob.key}
              knob={knob}
              value={voice[knob.key]}
              onChange={(v) => onChange({ [knob.key]: v } as Partial<Voice>)}
            />
          ))}
        </div>
      </Group>

      <Group title="End of speech">
        <div className="space-y-3">
          {END_OF_SPEECH.map((knob) => (
            <Tunable
              key={knob.key}
              knob={knob}
              value={voice[knob.key]}
              onChange={(v) => onChange({ [knob.key]: v } as Partial<Voice>)}
            />
          ))}
        </div>
      </Group>

      <Group title="Interruption">
        <Toggle
          checked={voice.interruption_enabled}
          onChange={(interruption_enabled) => onChange({ interruption_enabled })}
          label="Let the prospect interrupt"
          hint="Off means the agent talks over you to the end of every sentence, and the two interrupt durations above stop mattering."
        />
        {voice.interruption_enabled !== DEFAULTS.interruption_enabled && (
          <div className="flex justify-end">
            <Button
              variant="quiet"
              className="px-2 py-0.5 text-xs"
              onClick={() => onChange({ interruption_enabled: DEFAULTS.interruption_enabled })}
            >
              Reset to on
            </Button>
          </div>
        )}
      </Group>

      <Group title="Filler phrases">
        <Hint>
          One of these plays about 1.5 s into a turn that is still waiting on a tool, so a pricing
          lookup does not sound like a dropped call. They inherit the interruption setting above.
        </Hint>
        <ListEditor
          items={voice.filler_phrases}
          onChange={(filler_phrases) => onChange({ filler_phrases })}
          placeholder="One moment."
          addLabel="Add phrase"
          emptyNote="No phrases. A slow tool call will be heard as silence."
        />
        {JSON.stringify(voice.filler_phrases) !== JSON.stringify(DEFAULTS.filler_phrases) && (
          <div className="flex justify-end">
            <Button
              variant="quiet"
              className="px-2 py-0.5 text-xs"
              onClick={() => onChange({ filler_phrases: [...DEFAULTS.filler_phrases] })}
            >
              Reset to the three defaults
            </Button>
          </div>
        )}
      </Group>

      <Group title="Text to speech">
        <div className="space-y-4">
          <Field
            label="Vendor"
            hint="Leave empty to use Agora's managed preset, which supplies the credentials too. Name a vendor only when a preset cannot give you the voice you want."
          >
            <Input
              value={voice.tts_vendor}
              onChange={(e) => onChange({ tts_vendor: e.target.value })}
              placeholder="managed preset"
              className="font-mono"
            />
          </Field>

          <div>
            <p className="text-sm text-ink">Vendor parameters</p>
            <p className="mt-0.5 mb-2 text-xs text-faint">
              Passed straight through to the engine as tts.params — voice id, speed, region. Shapes
              differ per vendor, so this stays JSON rather than a form that would be wrong for
              every vendor but one.
            </p>
            <JsonField
              value={voice.tts_params}
              onApply={(parsed) => {
                if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed))
                  return "Expected a JSON object, for example { \"voice_id\": \"...\" }.";
                onChange({ tts_params: parsed as Record<string, unknown> });
                return null;
              }}
            />
          </div>
        </div>
      </Group>
    </div>
  );
}
