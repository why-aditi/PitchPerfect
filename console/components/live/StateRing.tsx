"use client";

import type { ReactNode } from "react";
import { cx } from "@/components/ui";
import type { CallState } from "@/lib/types";

/**
 * The call state, rendered so it survives a projector.
 *
 * Colour alone is not enough at the back of a room, so each state also gets its own
 * motion: connecting marches, listening breathes, thinking spins, speaking radiates.
 * A viewer who cannot read the label still knows which of the four they are looking at.
 */

export const STATE_COLOR: Record<CallState, string> = {
  idle: "var(--color-faint)",
  connecting: "var(--color-muted)",
  listening: "var(--color-listening)",
  thinking: "var(--color-thinking)",
  speaking: "var(--color-speaking)",
};

export const STATE_LABEL: Record<CallState, string> = {
  idle: "Not connected",
  connecting: "Connecting",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

const CSS = `
@keyframes pp-turn { to { transform: rotate(360deg); } }
@keyframes pp-march { to { stroke-dashoffset: -160; } }
@keyframes pp-breathe {
  0%, 100% { transform: scale(0.92); opacity: 0.28; }
  50%      { transform: scale(1.06); opacity: 0.55; }
}
@keyframes pp-radiate {
  from { transform: scale(0.78); opacity: 0.5; }
  to   { transform: scale(1.45); opacity: 0; }
}
@keyframes pp-bar {
  0%, 100% { transform: scaleY(0.22); }
  50%      { transform: scaleY(1); }
}
@media (prefers-reduced-motion: reduce) {
  .pp-turn, .pp-breathe, .pp-radiate, .pp-bar { animation: none !important; }
}
.pp-turn { transform-origin: 50% 50%; animation: pp-turn 1s linear infinite; }
.pp-slow { animation-duration: 3.2s; }
.pp-march { animation: pp-march 2.4s linear infinite; }
.pp-breathe { animation: pp-breathe 2.8s ease-in-out infinite; }
.pp-radiate { animation: pp-radiate 1.6s ease-out infinite; }
.pp-bar { transform-origin: 50% 100%; animation: pp-bar 0.6s ease-in-out infinite; }
`;

/** React hoists and de-duplicates this, so every ring on the page shares one copy. */
function RingStyles() {
  return (
    <style href="pitchpilot-state-ring" precedence="medium">
      {CSS}
    </style>
  );
}

export function StateRing({
  state,
  size = 112,
  children,
}: {
  state: CallState;
  size?: number;
  children?: ReactNode;
}) {
  const color = STATE_COLOR[state];
  const track = `color-mix(in oklab, ${color} 22%, transparent)`;

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <RingStyles />

      {state === "listening" && (
        <span
          className="pp-breathe absolute inset-[14%] rounded-full"
          style={{ background: `color-mix(in oklab, ${color} 30%, transparent)` }}
        />
      )}

      {state === "speaking" &&
        [0, 0.55].map((delay) => (
          <span
            key={delay}
            className="pp-radiate absolute inset-0 rounded-full border-2"
            style={{ borderColor: color, animationDelay: `${delay}s` }}
          />
        ))}

      <svg viewBox="0 0 100 100" className="absolute inset-0 h-full w-full">
        <circle cx="50" cy="50" r="45" fill="none" stroke={track} strokeWidth="3" />
        {state === "connecting" && (
          <circle
            className="pp-march"
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke={color}
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray="3 11"
          />
        )}
        {state === "thinking" && (
          <circle
            className="pp-turn"
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke={color}
            strokeWidth="4"
            strokeLinecap="round"
            strokeDasharray="70 213"
          />
        )}
        {(state === "listening" || state === "speaking") && (
          <circle
            className={cx(state === "listening" && "pp-turn pp-slow")}
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke={color}
            strokeWidth={state === "speaking" ? 4 : 3}
            strokeLinecap="round"
            strokeDasharray={state === "listening" ? "150 139" : undefined}
          />
        )}
      </svg>

      <div className="absolute inset-0 flex flex-col items-center justify-center">
        {children ?? (
          <span
            className="h-2.5 w-2.5 rounded-full"
            style={{ background: color, opacity: state === "idle" ? 0.5 : 1 }}
          />
        )}
      </div>
    </div>
  );
}

/**
 * Both parties, side by side and always visible. Barge-in is the product demo, and it is
 * only legible as an overlap — one indicator that switches between speakers would hide
 * the exact moment being demonstrated.
 */
export function SpeakingPair({
  agent,
  prospect,
  className,
}: {
  agent: boolean;
  prospect: boolean;
  className?: string;
}) {
  return (
    <div className={cx("space-y-1.5", className)}>
      <RingStyles />
      <Meter label="Agent" active={agent} color="var(--color-speaking)" />
      <Meter label="Prospect" active={prospect} color="var(--color-listening)" />
      {/* Kept in the layout at all times so the panel does not jump when it fires; hidden
          from the accessibility tree until it is true. */}
      <p
        aria-hidden={!(agent && prospect)}
        className={cx(
          "font-mono text-[10px] uppercase tracking-wider transition-opacity",
          agent && prospect ? "text-thinking opacity-100" : "opacity-0",
        )}
      >
        Barge-in — agent interrupted
      </p>
    </div>
  );
}

function Meter({ label, active, color }: { label: string; active: boolean; color: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <span
        className={cx(
          "w-16 shrink-0 font-mono text-[10px] uppercase tracking-wider transition-colors",
          active ? "text-ink" : "text-faint",
        )}
      >
        {label}
      </span>
      <span className="flex h-4 items-end gap-[3px]">
        {[0, 1, 2, 3, 4].map((i) => (
          <span
            key={i}
            className={cx("w-[3px] rounded-full", active && "pp-bar")}
            style={{
              height: 16,
              background: active ? color : "var(--color-line)",
              transform: active ? undefined : "scaleY(0.22)",
              transformOrigin: "50% 100%",
              animationDelay: `${i * 0.09}s`,
            }}
          />
        ))}
      </span>
    </div>
  );
}
