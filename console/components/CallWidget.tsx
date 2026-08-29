"use client";

import { useState, type ReactNode } from "react";
import { Button, cx } from "@/components/ui";
import { SpeakingPair, STATE_LABEL, StateRing } from "@/components/live/StateRing";
import { Transcript } from "@/components/live/Transcript";
import { clock, useCall } from "@/lib/useCall";

/**
 * The prospect's side of the call (PRD 10.1). All Agora lifecycle lives in useCall; what
 * is left here is the part a viewer judges — which of the four states the agent is in, and
 * who is talking over whom.
 */
export default function CallWidget({ agentId }: { agentId: string }) {
  const call = useCall({ kind: "call", agentId });
  const [asking, setAsking] = useState(false);
  const [denied, setDenied] = useState<string | null>(null);

  async function begin() {
    setDenied(null);
    setAsking(true);
    try {
      // The mic prompt is answered before the join, so a refusal costs nothing: no engine
      // agent has been started and no conversational minutes have been spent.
      const probe = await navigator.mediaDevices.getUserMedia({ audio: true });
      probe.getTracks().forEach((t) => t.stop());
    } catch {
      setDenied(
        "Microphone blocked. Allow it from the icon in the address bar, then try again.",
      );
      setAsking(false);
      return;
    }
    setAsking(false);
    await call.start();
  }

  const error = denied ?? call.error;

  if (call.state === "idle") {
    return (
      <div className="flex w-max max-w-[280px] flex-col items-end gap-2">
        {error && <ErrorNote>{error}</ErrorNote>}
        <button
          onClick={begin}
          disabled={asking}
          className={cx(
            "flex items-center gap-2 rounded-full bg-brand px-5 py-3 text-sm font-medium text-surface",
            "shadow-[0_8px_24px_-6px_rgba(91,140,255,0.6)] transition-colors hover:bg-brand/90",
            "disabled:cursor-progress disabled:bg-brand-dim disabled:text-muted",
          )}
        >
          <MicGlyph />
          {asking ? "Waiting for mic…" : "Talk to Sales"}
        </button>
      </div>
    );
  }

  const connecting = call.state === "connecting";

  return (
    <div className="w-[340px] rounded-2xl border border-line bg-panel p-4 shadow-[0_20px_50px_-12px_rgba(0,0,0,0.7)]">
      <div className="flex items-center gap-4">
        <StateRing state={call.state} size={84}>
          <span className="font-mono text-sm text-ink">{clock(call.seconds)}</span>
        </StateRing>

        <div className="min-w-0 flex-1">
          <p className="text-base font-medium text-ink">{STATE_LABEL[call.state]}</p>
          <p className="mb-2.5 text-xs text-faint">
            {connecting ? "Placing the call" : "Interrupt any time — it will stop."}
          </p>
          <SpeakingPair agent={call.agentSpeaking} prospect={call.prospectSpeaking} />
        </div>
      </div>

      {error && <ErrorNote className="mt-3">{error}</ErrorNote>}

      {call.transcript.length > 0 && (
        <div className="mt-3 flex h-44 flex-col border-t border-line-soft pt-3">
          <Transcript lines={call.transcript} dense empty={null} />
        </div>
      )}

      <div className="mt-3 flex gap-2">
        <Button
          variant="ghost"
          className="flex-1"
          onClick={call.toggleMute}
          disabled={connecting}
          aria-pressed={call.muted}
        >
          {call.muted ? "Unmute" : "Mute"}
        </Button>
        <Button variant="danger" className="flex-1" onClick={call.stop}>
          End call
        </Button>
      </div>

      <p className="mt-3 text-center text-[11px] leading-snug text-faint">
        You are speaking with an AI sales assistant. This call is transcribed.
      </p>
    </div>
  );
}

/** The 403 from /start-call lands here, and its text is the fix — never swallow it. */
function ErrorNote({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p
      role="alert"
      className={cx(
        "w-full rounded-lg border border-escalate/40 bg-escalate/10 px-3 py-2 text-left text-xs leading-snug text-escalate",
        className,
      )}
    >
      {children}
    </p>
  );
}

function MicGlyph() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3" />
    </svg>
  );
}
