"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";
import { STATE_LABEL, StateRing } from "@/components/live/StateRing";
import { Button, Dot, Field, Input, cx } from "@/components/ui";
import type { CallState } from "@/lib/types";

/** The four states a live call moves through, in the order a real call visits them. */
const CYCLE: CallState[] = ["connecting", "listening", "thinking", "speaking"];

const STATE_NOTE: Record<CallState, string> = {
  idle: "",
  connecting: "Token minted, channel joined, engine agent started.",
  listening: "Voice activity detection decides when a turn begins.",
  thinking: "Tools run first — prices and slots never come from memory.",
  speaking: "Interrupt any time. The agent stops mid-sentence.",
};

export default function Login() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // One orchestrated moment on the page: the ring walks the call, so the operator sees
  // the thing they are about to configure before they configure it.
  const [step, setStep] = useState(0);
  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;
    const t = setInterval(() => setStep((s) => (s + 1) % CYCLE.length), 2600);
    return () => clearInterval(t);
  }, []);
  const state = CYCLE[step];

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(password);
      router.push("/agents");
    } catch {
      setError("Wrong password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto grid w-full max-w-6xl flex-1 items-center gap-12 px-6 py-12 lg:grid-cols-[1.1fr_minmax(0,400px)] lg:gap-20">
      <section className="rise order-2 lg:order-1">
        <div className="flex items-center gap-8">
          <StateRing state={state} size={148}>
            <span className="font-display text-sm font-medium text-ink">{STATE_LABEL[state]}</span>
          </StateRing>
          <ol className="space-y-2">
            {CYCLE.map((s) => (
              <li
                key={s}
                className={cx(
                  "flex items-center gap-3 text-sm transition-colors",
                  s === state ? "text-ink" : "text-faint",
                )}
              >
                <span
                  className="h-1.5 w-1.5 rounded-full transition-opacity"
                  style={{
                    background: `var(--color-${s === "connecting" ? "muted" : s})`,
                    opacity: s === state ? 1 : 0.35,
                  }}
                />
                {STATE_LABEL[s]}
              </li>
            ))}
          </ol>
        </div>

        <h1 className="mt-10 max-w-xl font-display text-4xl font-semibold leading-[1.05] tracking-tight text-ink sm:text-5xl">
          A voice sales agent you can tune while it is on the phone.
        </h1>
        <p className="mt-5 max-w-lg text-base leading-relaxed text-muted">
          Set the persona, the prices it may quote and the moment it hands off to a person.
          Paste one script tag on any page. Then watch the call, the lead state and every
          tool call as they happen.
        </p>
        <p className="mt-6 min-h-5 text-sm text-faint" aria-live="polite">
          {STATE_NOTE[state]}
        </p>
      </section>

      <section className="order-1 lg:order-2">
        <form
          onSubmit={submit}
          className="rise rounded-2xl border border-line bg-panel p-6 shadow-float"
        >
          <h2 className="font-display text-xl font-semibold text-ink">Sign in</h2>
          <p className="mt-1.5 text-sm leading-relaxed text-muted">
            One operator password. It also guards the screens that store a Cal.com key or a
            HubSpot token on an agent.
          </p>

          <div className="mt-6 space-y-4">
            <Field label="Operator password">
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••"
                autoFocus
                autoComplete="current-password"
              />
            </Field>

            {error && (
              <p role="alert" className="flex items-center gap-2 text-sm text-escalate">
                <Dot tone="var(--color-escalate)" />
                {error}
              </p>
            )}

            <Button type="submit" disabled={busy || !password} className="w-full py-2.5">
              {busy ? "Checking…" : "Sign in"}
            </Button>
          </div>

          <p className="mt-5 text-xs leading-relaxed text-faint">
            The password is <code className="font-mono text-muted">CONSOLE_PASSWORD</code> in the
            backend environment.
          </p>
        </form>
      </section>
    </main>
  );
}
