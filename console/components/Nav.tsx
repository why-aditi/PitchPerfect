"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { logout } from "@/lib/api";
import { Button, cx } from "./ui";

/** The product mark: a level meter, because the thing being built is a voice. */
export function Mark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={cx("shrink-0", className)}>
      <rect width="24" height="24" rx="7" fill="currentColor" opacity="0.16" />
      <g fill="currentColor">
        <rect x="5.5" y="10" width="2" height="4" rx="1" opacity="0.55" />
        <rect x="9" y="6.5" width="2" height="11" rx="1" />
        <rect x="12.5" y="8.5" width="2" height="7" rx="1" opacity="0.8" />
        <rect x="16" y="10.75" width="2" height="2.5" rx="1" opacity="0.45" />
      </g>
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cx("font-semibold tracking-tight text-ink", className)}>
      Pitch<span className="text-brand">Pilot</span>
    </span>
  );
}

export function Nav() {
  const pathname = usePathname() ?? "";
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  const embedded = pathname.startsWith("/widget");

  // globals.css paints an opaque surface on <body>. Inside the embed iframe that reads as a
  // black rectangle around the launcher on someone else's page, and the widget route cannot
  // opt out from inside <body>. Undone on navigation so the console keeps its own ground.
  useEffect(() => {
    if (!embedded) return;
    document.body.classList.add("bg-transparent");
    return () => document.body.classList.remove("bg-transparent");
  }, [embedded]);

  if (embedded) return null;

  async function signOut() {
    setBusy(true);
    // The cookie is HttpOnly, so a failed logout call still leaves this browser with nothing
    // it can do but sign in again. Route either way rather than stranding the operator.
    try {
      await logout();
    } catch {
      /* already gone, or the backend is down */
    }
    router.push("/login");
  }

  const onLogin = pathname === "/login";

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface/85 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between gap-4 px-6">
        <Link
          href={onLogin ? "/login" : "/agents"}
          className="flex items-center gap-2.5 transition-opacity hover:opacity-80"
        >
          <Mark className="h-7 w-7 text-brand" />
          <Wordmark className="text-[15px]" />
          <span className="hidden border-l border-line pl-2.5 font-mono text-[10px] uppercase tracking-[0.16em] text-faint sm:inline">
            console
          </span>
        </Link>

        {!onLogin && (
          <Button variant="quiet" onClick={signOut} disabled={busy} className="px-2.5 py-1.5 text-xs">
            {busy ? "Signing out…" : "Sign out"}
          </Button>
        )}
      </div>
    </header>
  );
}
