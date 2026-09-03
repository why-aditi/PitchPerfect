"use client";

import { use, useEffect, useRef, useState } from "react";
import { Badge, Button, Card, Empty, cx } from "@/components/ui";
import { SpeakingPair, STATE_LABEL, StateRing } from "@/components/live/StateRing";
import { subscribe } from "@/lib/events";
import type { RtmEvent } from "@/lib/types";
import { clock, useCall } from "@/lib/useCall";

type Escalation = {
  key: string;
  session_id: string;
  reason: string;
  summary: string;
  channel: string;
  ts: number;
};

export default function Escalations({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const [queue, setQueue] = useState<Escalation[]>([]);
  const [closed, setClosed] = useState<string[]>([]);
  const [channel, setChannel] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  // A rep joins to talk, so this one publishes a microphone. It is still the same channel
  // the prospect and the agent are already in — a fresh /start-call would mint a token for
  // a different channel and could not be used to join this one.
  const call = useCall({ kind: "observe", agentId: id, channel: channel ?? "", mic: true });
  const callRef = useRef(call);
  // Read from the subscriber and from the join/leave handlers, which must not re-bind on
  // every volume tick.
  useEffect(() => {
    callRef.current = call;
  });

  useEffect(
    () =>
      subscribe(id, (e: RtmEvent) => {
        if (e.type === "escalation") {
          setQueue((q) => [
            { key: `${e.session_id}-${e.ts}`, session_id: e.session_id, ...e.data, ts: e.ts },
            ...q,
          ]);
        }
        // A rep should not be offered a channel the engine has already left.
        if (e.type === "call_ended") setClosed((c) => [...c, e.session_id]);
      }),
    [id],
  );

  // The wait is the number a rep is judged on, so it counts up rather than freezing at the
  // moment the escalation arrived.
  useEffect(() => {
    if (queue.length === 0) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [queue.length]);

  useEffect(() => {
    if (channel) void callRef.current.start();
  }, [channel]);

  async function join(next: string) {
    // Retrying the channel that just failed: it has not changed, so the effect that
    // watches it will not fire again on its own.
    if (channel === next) {
      await callRef.current.start();
      return;
    }
    // One channel at a time: two live microphones from one rep is two conversations.
    if (channel) await callRef.current.stop();
    setChannel(next);
  }

  async function leave() {
    await callRef.current.stop();
    setChannel(null);
  }

  // A join that failed is not a join, whatever the channel state still says.
  const inCall = channel !== null && !call.error;

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-8 lg:px-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight text-ink">Escalations</h1>
          <p className="mt-1 font-mono text-xs text-faint">{id}</p>
        </div>
        {queue.length > 0 && (
          <Badge tone={inCall ? "live" : "warn"}>
            {queue.length} in queue{inCall ? " · joined" : ""}
          </Badge>
        )}
      </header>

      {call.error && (
        <p
          role="alert"
          className="mt-6 rounded-lg border border-escalate/40 bg-escalate/10 px-3 py-2 text-sm text-escalate"
        >
          Could not join {channel}: {call.error}
        </p>
      )}

      {queue.length === 0 ? (
        <div className="mt-8">
          <Empty>
            <p className="mx-auto max-w-md leading-relaxed">
              Nothing waiting. An escalation arrives when the agent calls{" "}
              <code className="font-mono text-ink">escalate_to_human</code> — the prospect
              asks for a person, the deal crosses the seat threshold set on the Persona tab,
              or a trust question comes up that the agent will not answer alone.
            </p>
            <p className="mx-auto mt-3 max-w-md leading-relaxed text-faint">
              Each one arrives with a written summary, so you have the context before you
              speak. Joining puts you in the same channel as the prospect and the agent.
            </p>
          </Empty>
        </div>
      ) : (
        <ul className="mt-8 space-y-4">
          {queue.map((e) => {
            const joined = inCall && channel === e.channel;
            const ended = closed.includes(e.session_id);
            return (
              <li key={e.key}>
                <Card
                  className={cx(
                    "rise p-5 transition-colors",
                    joined && "border-listening/40",
                  )}
                >
                <div className="flex flex-wrap items-baseline justify-between gap-3">
                  <span className="font-display text-base font-semibold text-ink">{e.reason}</span>
                  <span className="text-xs text-faint">
                    <span className="font-mono">{e.channel}</span>
                    {" — "}
                    {ended ? "call ended" : `${waited(e.ts, now)} waiting`}
                  </span>
                </div>

                <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-muted">
                  {e.summary}
                </p>

                {joined ? (
                  <div className="mt-4 flex items-center gap-4 rounded-lg border border-line bg-raised p-3">
                    <StateRing state={call.state} size={48} />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-ink">{STATE_LABEL[call.state]}</p>
                      <p className="font-mono text-xs text-faint">
                        {clock(call.seconds)} in channel
                        {call.muted && " · muted"}
                      </p>
                    </div>
                    <SpeakingPair
                      agent={call.agentSpeaking}
                      prospect={call.prospectSpeaking}
                      className="hidden sm:block"
                    />
                    <div className="flex flex-col gap-2">
                      <Button variant="ghost" onClick={call.toggleMute} aria-pressed={call.muted}>
                        {call.muted ? "Unmute" : "Mute"}
                      </Button>
                      <Button variant="danger" onClick={leave}>
                        Leave
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="mt-4 flex items-center gap-3">
                    <Button onClick={() => join(e.channel)} disabled={ended}>
                      Join call with microphone
                    </Button>
                    {ended ? (
                      <span className="text-xs text-faint">
                        This call is over. The summary stays for the CRM follow-up.
                      </span>
                    ) : (
                      inCall && (
                        <span className="text-xs text-faint">
                          Joining leaves {channel} first.
                        </span>
                      )
                    )}
                  </div>
                )}
                </Card>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}

function waited(since: number, now: number): string {
  return clock(Math.max(0, Math.floor((now - since) / 1000)));
}
