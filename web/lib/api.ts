import type { Pricing, Session } from "./types";

const post = <T,>(path: string, body: unknown): Promise<T> =>
  fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => {
    if (!r.ok) throw new Error(`${path} failed: ${r.status}`);
    return r.json() as Promise<T>;
  });

export const startCall = (pageContext = "pricing") =>
  post<Session>("/start-call", { page_context: pageContext });

export const stopCall = (sessionId: string) =>
  post<{ ok: boolean }>("/stop-call", { session_id: sessionId });

export async function getPricing(): Promise<Pricing> {
  const backend = process.env.BACKEND_URL ?? "http://localhost:8000";
  const r = await fetch(`${backend}/pricing`, { cache: "no-store" });
  if (!r.ok) throw new Error(`pricing failed: ${r.status}`);
  return r.json();
}
