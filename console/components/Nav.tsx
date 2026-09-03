"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "./theme";
import { Dot, cx } from "./ui";

/**
 * The product mark: the call-state ring from the live screen, with a level meter inside —
 * the two things an operator watches. Drawn in one colour so it sits on either theme and
 * inside the brand-tinted disc without a second palette.
 */
export function Mark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cx("shrink-0", className)}>
      <circle cx="16" cy="16" r="15" fill="currentColor" />
      <circle cx="16" cy="16" r="11.5" fill="none" stroke="#fff" strokeWidth="1.5" opacity="0.55" strokeDasharray="60 12.3" strokeLinecap="round" transform="rotate(-70 16 16)" />
      <g fill="#fff">
        <rect x="9.5" y="13.5" width="2.2" height="5" rx="1.1" opacity="0.7" />
        <rect x="13.1" y="9.5" width="2.2" height="13" rx="1.1" />
        <rect x="16.7" y="11.5" width="2.2" height="9" rx="1.1" opacity="0.9" />
        <rect x="20.3" y="14" width="2.2" height="4" rx="1.1" opacity="0.6" />
      </g>
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cx("font-display font-semibold tracking-tight text-ink", className)}>
      PitchPilot
    </span>
  );
}

/**
 * Whether the FastAPI side answers, polled through the same-origin proxy. The console is
 * useless without it, so the header says so before a save fails with a vague error.
 */
function useBackend(): "up" | "down" | null {
  const [state, setState] = useState<"up" | "down" | null>(null);
  useEffect(() => {
    let alive = true;
    const probe = async () => {
      try {
        const r = await fetch("/api/openapi.json", { method: "HEAD", cache: "no-store" });
        if (alive) setState(r.ok ? "up" : "down");
      } catch {
        if (alive) setState("down");
      }
    };
    void probe();
    const t = setInterval(probe, 30_000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);
  return state;
}

export function Nav() {
  const pathname = usePathname() ?? "";
  const backend = useBackend();

  const embedded = pathname.startsWith("/widget");

  // globals.css paints an opaque surface on <body>. Inside the embed iframe that reads as a
  // solid rectangle around the launcher on someone else's page, and the widget route cannot
  // opt out from inside <body>. Undone on navigation so the console keeps its own ground.
  useEffect(() => {
    if (!embedded) return;
    document.documentElement.style.background = "transparent";
    document.body.style.background = "transparent";
    return () => {
      document.documentElement.style.background = "";
      document.body.style.background = "";
    };
  }, [embedded]);

  if (embedded) return null;

  // Only /login reaches here; everything signed-in lives inside Shell's sidebar.
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-4 px-6">
        <span className="flex items-center gap-2.5">
          <Mark className="h-8 w-8 text-brand" />
          <Wordmark className="text-[17px]" />
          <span className="hidden rounded-md border border-line px-1.5 py-0.5 text-[11px] font-medium text-muted sm:inline">
            Console
          </span>
        </span>

        <div className="ml-auto flex items-center gap-3">
          <span
            className="hidden items-center gap-2 rounded-full border border-line bg-panel py-1 pl-2.5 pr-3 text-xs text-muted sm:flex"
            title="FastAPI backend, via the /api proxy"
          >
            <Dot
              tone={
                backend === "up"
                  ? "var(--color-listening)"
                  : backend === "down"
                    ? "var(--color-escalate)"
                    : "var(--color-faint)"
              }
              pulse={backend === "up"}
            />
            {backend === "up" ? "Backend online" : backend === "down" ? "Backend offline" : "Checking backend"}
          </span>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
