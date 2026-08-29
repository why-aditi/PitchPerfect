"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";
import { Mark, Wordmark } from "@/components/Nav";
import { Button, Card, Dot, Field, Input } from "@/components/ui";

export default function Login() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
    <main className="flex flex-1 items-center justify-center px-6 py-16">
      <div className="rise w-full max-w-[380px]">
        <div className="flex flex-col items-center text-center">
          <Mark className="h-11 w-11 text-brand" />
          <h1 className="mt-4 text-lg">
            <Wordmark /> <span className="text-muted">console</span>
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            One shared operator password gates every route in here, including the ones that
            can write a Cal.com key or a HubSpot token onto an agent.
          </p>
        </div>

        <Card className="mt-6 p-5">
          <form onSubmit={submit} className="space-y-4">
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

            <Button type="submit" disabled={busy || !password} className="w-full">
              {busy ? "Checking…" : "Sign in"}
            </Button>
          </form>
        </Card>

        <p className="mt-4 text-center font-mono text-[11px] text-faint">
          CONSOLE_PASSWORD · set in the backend environment
        </p>
      </div>
    </main>
  );
}
