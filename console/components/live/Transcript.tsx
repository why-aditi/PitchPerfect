"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { cx } from "@/components/ui";
import type { TranscriptLine } from "@/lib/transcript";

/**
 * The engine's transcript, rendered from the data channel (PRD 6.2).
 *
 * Two rules the rest of the screen depends on: a line that is still being spoken must not
 * look settled, and the view follows the newest line only while the reader is already at
 * the bottom — an operator who scrolled up to re-read something is not fighting the feed.
 */
export function Transcript({
  lines,
  dense,
  empty,
  className,
}: {
  lines: TranscriptLine[];
  dense?: boolean;
  empty: ReactNode;
  className?: string;
}) {
  const box = useRef<HTMLDivElement | null>(null);
  const [pinned, setPinned] = useState(true);

  useEffect(() => {
    if (pinned && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [lines, pinned]);

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div
        ref={box}
        onScroll={(e) => {
          const el = e.currentTarget;
          setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 40);
        }}
        className={cx(
          "min-h-0 flex-1 overflow-y-auto",
          dense ? "space-y-2 pr-1" : "space-y-3 pr-2",
          className,
        )}
      >
        {lines.length === 0 ? (
          <div className="flex h-full items-center justify-center px-4 py-6 text-center text-sm text-muted">
            {empty}
          </div>
        ) : (
          lines.map((line) => <Line key={line.id} line={line} dense={dense} />)
        )}
      </div>

      {!pinned && lines.length > 0 && (
        <button
          onClick={() => setPinned(true)}
          className="absolute bottom-2 left-1/2 -translate-x-1/2 rounded-full border border-line bg-panel px-3 py-1 text-xs text-muted shadow-sm transition-colors hover:text-ink"
        >
          Jump to latest
        </button>
      )}
    </div>
  );
}

function Line({ line, dense }: { line: TranscriptLine; dense?: boolean }) {
  const agent = line.role === "agent";
  return (
    <div className="rise flex gap-3">
      <span
        className={cx(
          "shrink-0 pt-px text-xs font-medium",
          dense ? "w-14" : "w-20",
          agent ? "text-speaking" : "text-listening",
        )}
      >
        {agent ? "Agent" : "Prospect"}
      </span>
      <p
        className={cx(
          dense ? "text-[13px] leading-snug" : "text-sm leading-relaxed",
          line.final ? "text-ink" : "italic text-muted",
        )}
      >
        {line.text}
        {!line.final && (
          <span className="ml-1 inline-block h-3 w-px translate-y-[2px] animate-pulse bg-muted align-middle" />
        )}
      </p>
    </div>
  );
}
