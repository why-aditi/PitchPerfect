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
export default function CallWidget({
  agentId,
  pageOrigin,
}: {
  agentId: string;
  /** The site that embedded us. The iframe's own Origin only ever names the console. */
  pageOrigin?: string;
}) {
  const call = useCall({ kind: "call", agentId, pageOrigin });
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
          // Its own two tokens, not ink and white. This button is the only part of the
          // product that paints onto someone else's page, and it is the one surface whose
          // contrast we cannot compute from in here — so it is chosen per theme rather
          // than derived from the panel, which in a dark theme would make it near-white
          // text on a near-white pill.
          //
          // The hairline ring is the floor. Every other ratio in a theme is against our
          // own panel and therefore guaranteed; this one is against pixels we will never
          // see, so the ring is what stops the launcher dissolving into a host whose
          // background happens to match it. shadow-float cannot do that job — it compiles
          // to a fixed black and is invisible on a dark page.
          className={cx(
            "flex items-center gap-2 rounded-[var(--launcher-radius,9999px)] px-5 py-3",
            "bg-launcher text-sm font-medium text-launcher-ink",
            "ring-1 ring-black/10 shadow-float transition-colors hover:bg-launcher/90",
            "disabled:cursor-progress disabled:bg-launcher/40 disabled:text-launcher-ink/80",
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
    <div className="w-[340px] rounded-[var(--panel-radius,1rem)] border border-line bg-panel p-4 shadow-float">
      <div className="flex items-center gap-4">
        <StateRing state={call.state} size={84}>
          <span className="font-mono text-sm text-ink">{clock(call.seconds)}</span>
        </StateRing>

        <div className="min-w-0 flex-1">
          <p className="font-display text-base font-semibold text-ink">{STATE_LABEL[call.state]}</p>
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
