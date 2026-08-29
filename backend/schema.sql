-- Applied on startup with create-if-not-exists. No migration tool: agent config is a
-- single jsonb column, so adding a builder field never changes this file.

CREATE TABLE IF NOT EXISTS agents (
  id              text PRIMARY KEY,
  name            text NOT NULL,
  config          jsonb NOT NULL,
  secrets         jsonb NOT NULL DEFAULT '{}'::jsonb,
  allowed_origins text[] NOT NULL DEFAULT '{}',
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS calls (
  session_id text PRIMARY KEY,
  agent_id   text NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  started_at timestamptz NOT NULL DEFAULT now(),
  ended_at   timestamptz,
  duration_s int,
  outcome    text,
  lead_state jsonb
);

CREATE INDEX IF NOT EXISTS calls_agent_started ON calls (agent_id, started_at DESC);
