"use client";

import { use, useEffect, useRef, useState } from "react";
import { Badge, Button, Card, SectionLabel, cx } from "@/components/ui";
import { LeadPanel } from "@/components/live/LeadPanel";
import { Outcomes, ToolChips, type Outcome, type ToolCall } from "@/components/live/Signals";
import { SpeakingPair, STATE_LABEL, StateRing } from "@/components/live/StateRing";
import { Transcript } from "@/components/live/Transcript";
import { DEMO_SESSION, demoScript } from "@/components/live/demoScript";
import { subscribe } from "@/lib/events";
import { applyLine, type TranscriptLine } from "@/lib/transcript";
import { channelFor, type LeadState, type RtmEvent } from "@/lib/types";
import { clock, useCall } from "@/lib/useCall";

const DEV = process.env.NODE_ENV !== "production";
const TOOL_CAP = 12;

type Phase = "waiting" | "live" | "ended";

export default function Live({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const [lead, setLead] = useState<LeadState | null>(null);
  const [changed, setChanged] = useState<string[]>([]);
  const [version, setVersion] = useState(0);
  const [tools, setTools] = useState<ToolCall[]>([]);
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);
  const [session, setSession] = useState<string | null>(null);
  const [channel, setChannel] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("waiting");
  const [endedAfter, setEndedAfter] = useState<number | null>(null);
  const [replayLines, setReplayLines] = useState<TranscriptLine[]>([]);
  const [replay, setReplay] = useState(false);

  const previous = useRef<LeadState | null>(null);
  const sessionRef = useRef<string | null>(null);

  // A call placed from this screen, with the operator's own microphone. It goes through
  // /start-call exactly like the widget does, so the console's origin must be on the
  // agent's allowed list — the 403 text says so if it is not.
  const test = useCall({ kind: "call", agentId: id });
  const testing = test.state !== "idle";
  const [asking, setAsking] = useState(false);
  const [denied, setDenied] = useState<string | null>(null);

  async function beginTest() {
    setDenied(null);
    setAsking(true);
    try {
      const probe = await navigator.mediaDevices.getUserMedia({ audio: true });
      probe.getTracks().forEach((t) => t.stop());
    } catch {
      setDenied("Microphone blocked. Allow it from the icon in the address bar, then try again.");
      setAsking(false);
      return;
    }
    setAsking(false);
    await test.start();
  }

  // PRD 6.2: the engine hands transcripts to whoever is in the channel and the backend
  // never republishes them, so reading one means joining — silently, without a microphone.
  const call = useCall({ kind: "observe", agentId: id, channel: channel ?? "", mic: false });
  const callRef = useRef(call);
  // Read from the subscriber and from effects that must not re-fire on every volume tick.
  useEffect(() => {
    callRef.current = call;
  });

  useEffect(
    () =>
      subscribe(id, (e: RtmEvent) => {
        // The first event of a session is what tells the console a call exists at all.
        if (sessionRef.current !== e.session_id) {
          sessionRef.current = e.session_id;
          previous.current = null;
          setSession(e.session_id);
          setLead(null);
          setChanged([]);
          setTools([]);
          setOutcomes([]);
          setEndedAfter(null);
          setPhase("live");
          setChannel(e.session_id === DEMO_SESSION ? null : channelFor(e.session_id));
        }

        switch (e.type) {
          case "lead_state": {
            const before = previous.current;
            setChanged(
              before
                ? Object.keys(e.data).filter(
                    (k) =>
                      JSON.stringify(e.data[k as keyof LeadState]) !==
                      JSON.stringify(before[k as keyof LeadState]),
                  )
                : Object.keys(e.data),
            );
            previous.current = e.data;
            setLead(e.data);
            setVersion((v) => v + 1);
            break;
          }
          case "tool_call":
            setTools((t) =>
              [
                { name: e.data.name, result_summary: e.data.result_summary, ts: e.ts },
                ...t,
              ].slice(0, TOOL_CAP),
            );
            break;
          case "outcome":
            setOutcomes((o) => [{ kind: e.data.kind, ts: e.ts }, ...o]);
            break;
          case "call_ended":
            setPhase("ended");
            setEndedAfter(e.data.duration_s);
            void callRef.current.stop();
            break;
          case "escalation":
            break;
        }
      }),
    [id],
  );

  useEffect(() => {
    if (phase === "live" && channel && !testing) void callRef.current.start();
  }, [phase, channel, testing]);

  /* ------------------------------------------------------------------ replay */

  const timers = useRef<number[]>([]);
  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach(clearTimeout);
  }, []);

  function runReplay() {
    timers.current.forEach(clearTimeout);
    timers.current.length = 0;
    sessionRef.current = null;
    setReplay(true);
    setReplayLines([]);
    const emit = (window as unknown as { emit?: (e: RtmEvent) => void }).emit;

    for (const step of demoScript(Date.now())) {
      const line = step.line;
      const event = step.event;
      timers.current.push(
        window.setTimeout(() => {
          if (event) emit?.(event);
          if (line) setReplayLines((lines) => applyLine(lines, line));
        }, step.at),
      );
    }
  }

  /* ------------------------------------------------------------------- view */

  const active = testing ? test : call;
  const lines = replay ? replayLines : active.transcript;
  const attaching = active.state === "connecting";

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-8 lg:px-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight text-ink">Live call</h1>
          <p className="mt-1 font-mono text-xs text-faint">
            {id}
            {session && <span className="text-muted"> · {session}</span>}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {replay ? (
            <Badge tone="warn">Replay</Badge>
          ) : phase === "live" ? (
            <Badge tone="live">In progress</Badge>
          ) : phase === "ended" ? (
            <Badge tone="neutral">Ended</Badge>
          ) : (
            <Badge tone="neutral">Waiting for a call</Badge>
          )}
          {testing ? (
            <>
              <Button variant="ghost" onClick={test.toggleMute} aria-pressed={test.muted} className="px-3 py-1.5 text-xs">
                {test.muted ? "Unmute" : "Mute"}
              </Button>
              <Button variant="danger" onClick={() => void test.stop()} className="px-3 py-1.5 text-xs">
                End test call
              </Button>
            </>
          ) : (
            <>
              {DEV && (
                <Button variant="quiet" onClick={runReplay} className="px-2 text-xs">
                  Replay demo call
                </Button>
              )}
              <Button onClick={beginTest} disabled={asking || replay} className="px-3 py-1.5 text-xs">
                <MicGlyph />
                {asking ? "Waiting for mic…" : "Test call"}
              </Button>
            </>
          )}
        </div>
      </header>

      {(denied || (testing && test.error)) && (
        <p role="alert" className="mt-4 rounded-lg border border-escalate/40 bg-escalate/10 px-3 py-2 text-sm text-escalate">
          {denied ?? test.error}
        </p>
      )}

      <div className="mt-6 grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-5">
          <Card className="flex h-[520px] flex-col p-5">
            <div className="flex items-center gap-4 border-b border-line-soft pb-4">
              <StateRing state={replay ? "listening" : active.state} size={64} />
              <div className="flex-1">
                <p className="font-display text-lg font-semibold text-ink">
                  {replay ? "Scripted replay" : STATE_LABEL[active.state]}
                </p>
                <p className="font-mono text-xs text-faint">
                  {replay
                    ? "the PRD 15.1 acceptance call"
                    : testing
                      ? `test call from this console · ${clock(test.seconds)}${test.muted ? " · muted" : ""}`
                      : channel
                        ? `${channel} · ${clock(call.seconds)}`
                        : "no channel yet"}
                </p>
              </div>
              <SpeakingPair
                agent={active.agentSpeaking}
                prospect={active.prospectSpeaking}
                className="hidden sm:block"
              />
            </div>

            <div className="flex items-baseline justify-between pt-4">
              <SectionLabel>Transcript</SectionLabel>
              {replay && (
                <Badge tone="warn">Scripted — not a live call</Badge>
              )}
            </div>

            {call.error && !replay && (
              <p
                role="alert"
                className="mb-3 rounded-lg border border-escalate/40 bg-escalate/10 px-3 py-2 text-sm text-escalate"
              >
                Could not join {channel}: {call.error}
                <button
                  onClick={() => void call.start()}
                  className="ml-2 underline underline-offset-2"
                >
                  Retry
                </button>
              </p>
            )}

            <Transcript
              lines={lines}
              empty={
                attaching ? (
                  <span className="text-sm text-muted">
                    Attaching to <span className="font-mono">{channel}</span>…
                  </span>
                ) : phase === "ended" ? (
                  "The call ended before anything was transcribed."
                ) : (
                  <span className="max-w-sm space-y-3 leading-relaxed">
                    <span className="block text-ink">No call in progress.</span>
                    <span className="block">
                      Talk to the agent right here with your microphone, or start a call from a
                      page that carries the embed snippet — this screen attaches either way.
                    </span>
                    <span className="flex flex-wrap justify-center gap-2 pt-1">
                      <button
                        type="button"
                        onClick={beginTest}
                        disabled={asking}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-ink px-3 py-1.5 text-xs font-medium text-surface transition-colors hover:bg-ink/85 disabled:opacity-60"
                      >
                        <MicGlyph />
                        {asking ? "Waiting for mic…" : "Test call from here"}
                      </button>
                      <a
                        href="http://localhost:3000"
                        target="_blank"
                        rel="noreferrer"
                        className="rounded-lg border border-line bg-panel px-3 py-1.5 text-xs text-ink transition-colors hover:border-ink/40"
                      >
                        Open the demo site
                      </a>
                      {DEV && (
                        <button
                          type="button"
                          onClick={runReplay}
                          className="rounded-lg border border-line bg-panel px-3 py-1.5 text-xs text-ink transition-colors hover:border-ink/40"
                        >
                          Replay a scripted call
                        </button>
                      )}
                    </span>
                  </span>
                )
              }
            />
          </Card>

          <Card className="p-4">
            <SectionLabel>Tool calls</SectionLabel>
            <div className="max-h-[168px] overflow-y-auto pr-1">
              <ToolChips calls={tools} />
            </div>
          </Card>
        </div>

        <div className="space-y-5">
          {(outcomes.length > 0 || endedAfter !== null) && (
            <Card className="p-4">
              <SectionLabel>Outcome</SectionLabel>
              <Outcomes outcomes={outcomes} endedAfter={endedAfter} />
            </Card>
          )}

          <Card className={cx("p-4", phase === "live" && "rise")}>
            <SectionLabel>Lead state</SectionLabel>
            <LeadPanel lead={lead} changed={changed} version={version} />
          </Card>
        </div>
      </div>
    </main>
  );
}

function MicGlyph() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3" />
    </svg>
  );
}
