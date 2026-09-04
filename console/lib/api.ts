import type { Agent, AgentConfig, AgentSummary, CallRecord, SecretsSet, Session } from "./types";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (r.status === 401) {
    // A hard navigation, not router.push: the session cookie is gone, so every screen's
    // loaded agent config and event subscription is now stale. Tearing the document down
    // is the point. (This runs in a plain async function, outside any render.)
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = "/login";
    throw new Error("not signed in");
  }
  if (!r.ok) throw new Error(await reason(r, path));
  return r.json() as Promise<T>;
}

/**
 * FastAPI puts the useful part in `detail` — a string for our own HTTPExceptions, a list of
 * field errors when a config fails Pydantic validation. Throwing the status alone would hide
 * exactly the message the operator needs: which field of the agent config was rejected, or
 * which origin was refused.
 */
async function reason(r: Response, path: string): Promise<string> {
  try {
    const body = (await r.json()) as { detail?: unknown };
    const detail = body.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((e) => {
          const at = Array.isArray((e as { loc?: unknown[] }).loc)
            ? (e as { loc: unknown[] }).loc.slice(1).join(".")
            : "";
          const msg = String((e as { msg?: unknown }).msg ?? "invalid");
          return at ? `${at}: ${msg}` : msg;
        })
        .join("; ");
    }
  } catch {
    // A gateway error or a dropped tunnel answers with HTML, not JSON.
  }
  return `${path} failed: ${r.status}`;
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

export const listCalls = (id: string) => call<CallRecord[]>(`/console/agents/${id}/calls`);

/**
 * A token for a channel that already exists, so the live and rep views can join a call
 * in progress. PRD 6.2 freezes transcripts onto the data channel and forbids the backend
 * republishing them, so being in the channel is the only way to read one. Operator-gated:
 * this mints RTC credentials for someone else's live conversation.
 */
export const observeChannel = (agent_id: string, channel: string) =>
  call<Session>("/console/observe", {
    method: "POST",
    body: JSON.stringify({ agent_id, channel }),
  });

export const deleteAgent = (id: string) =>
  call<{ ok: boolean }>(`/console/agents/${id}`, { method: "DELETE" });

// Call lifecycle, used by the widget route rather than by the console screens.
export const startCall = (agent_id: string, page_context = "pricing", page_origin?: string) =>
  call<Session>("/start-call", {
    method: "POST",
    // The prospect's own timezone, straight off the browser. Without it check_slots ran in
    // UTC until someone said otherwise, so the agent spent a turn asking and, before that
    // answer arrived, read UTC slots aloud — one call offered "Friday at 3:30am" to a
    // prospect in India. resolvedOptions().timeZone is an IANA name every browser has;
    // the backend resolves it leniently and falls back to UTC, so a wrong or missing one
    // is exactly as good as not sending it.
    body: JSON.stringify({
      agent_id,
      page_context,
      page_origin,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    }),
  });

export const stopCall = (session_id: string) =>
  call<{ ok: boolean }>("/stop-call", { method: "POST", body: JSON.stringify({ session_id }) });
