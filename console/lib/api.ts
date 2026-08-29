import type { Agent, AgentConfig, AgentSummary, SecretsSet, Session } from "./types";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (r.status === 401) {
    window.location.href = "/login";
    throw new Error("not signed in");
  }
  if (!r.ok) throw new Error(`${path} failed: ${r.status}`);
  return r.json() as Promise<T>;
}

export const login = (password: string) =>
  call<{ ok: boolean }>("/console/login", { method: "POST", body: JSON.stringify({ password }) });

export const logout = () => call<{ ok: boolean }>("/console/logout", { method: "POST" });

export const listAgents = () => call<AgentSummary[]>("/console/agents");

export const getAgent = (id: string) => call<Agent>(`/console/agents/${id}`);

export const createAgent = (name: string, config: AgentConfig, allowed_origins: string[]) =>
  call<{ id: string }>("/console/agents", {
    method: "POST",
    body: JSON.stringify({ name, config, allowed_origins }),
  });

export const saveAgent = (id: string, name: string, config: AgentConfig, allowed_origins: string[]) =>
  call<{ ok: boolean }>(`/console/agents/${id}`, {
    method: "PUT",
    body: JSON.stringify({ name, config, allowed_origins }),
  });

/** Write-only. The response is the mask, never the values just sent. */
export const saveSecrets = (id: string, secrets: Record<string, string | null>) =>
  call<SecretsSet>(`/console/agents/${id}/secrets`, {
    method: "PUT",
    body: JSON.stringify(secrets),
  });

export const deleteAgent = (id: string) =>
  call<{ ok: boolean }>(`/console/agents/${id}`, { method: "DELETE" });

// Call lifecycle, used by the widget route rather than by the console screens.
export const startCall = (agent_id: string, page_context = "pricing") =>
  call<Session>("/start-call", {
    method: "POST",
    body: JSON.stringify({ agent_id, page_context }),
  });

export const stopCall = (session_id: string) =>
  call<{ ok: boolean }>("/stop-call", { method: "POST", body: JSON.stringify({ session_id }) });
