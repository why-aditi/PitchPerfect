import type { Pricing } from "./types";

/**
 * The demo site talks to the backend for exactly one thing: the pricing table.
 * Starting and stopping calls is the embedded widget's job, inside its own iframe.
 */
export async function getPricing(agentId: string): Promise<Pricing> {
  const backend = process.env.BACKEND_URL ?? "http://localhost:8000";
  const r = await fetch(`${backend}/agents/${agentId}/pricing`, { cache: "no-store" });
  if (!r.ok) throw new Error(`pricing failed: ${r.status}`);
  return r.json();
}
