"""Postgres access. asyncpg, no ORM, no migration tool.

Secrets never leave this module in readable form except through get_secrets(), which
only the call runtime uses. Console reads go through get_agent(), which drops them.
"""
import json
import os
from pathlib import Path

import asyncpg

from .models import AgentConfig, AgentSecrets

DATABASE_URL = os.getenv("DATABASE_URL", "")
_pool: asyncpg.Pool | None = None


async def connect() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        # Supabase's transaction pooler (:6543) multiplexes sessions, so asyncpg's prepared
        # statements collide across connections with "prepared statement already exists".
        # The session pooler (:5432) is unaffected. Detect rather than disable everywhere,
        # since prepared statements are worth keeping when they work.
        transaction_pooler = ":6543" in DATABASE_URL
        _pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=1, max_size=5,
            statement_cache_size=0 if transaction_pooler else 100)
        await _pool.execute((Path(__file__).parent / "schema.sql").read_text())
    return _pool


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def list_agents() -> list[dict]:
    pool = await connect()
    rows = await pool.fetch("""
        SELECT a.id, a.name, a.updated_at, count(c.session_id) AS call_count,
               max(c.ended_at) FILTER (WHERE c.outcome IS NOT NULL) AS last_outcome_at
        FROM agents a LEFT JOIN calls c ON c.agent_id = a.id
        GROUP BY a.id ORDER BY a.updated_at DESC
    """)
    return [dict(r) for r in rows]


async def get_agent(agent_id: str) -> dict | None:
    """Console-safe read: config and origins, never the secrets."""
    pool = await connect()
    row = await pool.fetchrow(
        "SELECT id, name, config, allowed_origins, secrets FROM agents WHERE id = $1", agent_id)
    if row is None:
        return None
    return {"id": row["id"], "name": row["name"],
            "config": AgentConfig(**json.loads(row["config"])),
            "allowed_origins": list(row["allowed_origins"]),
            "secrets_set": AgentSecrets(**json.loads(row["secrets"])).masked()}


async def get_secrets(agent_id: str) -> AgentSecrets:
    """Runtime-only read. Never route this through a response model."""
    pool = await connect()
    row = await pool.fetchval("SELECT secrets FROM agents WHERE id = $1", agent_id)
    return AgentSecrets(**json.loads(row)) if row else AgentSecrets()


async def save_agent(agent_id: str, name: str, config: AgentConfig,
                     allowed_origins: list[str]) -> None:
    pool = await connect()
    await pool.execute("""
        INSERT INTO agents (id, name, config, allowed_origins)
        VALUES ($1, $2, $3::jsonb, $4)
        ON CONFLICT (id) DO UPDATE
          SET name = $2, config = $3::jsonb, allowed_origins = $4, updated_at = now()
    """, agent_id, name, config.model_dump_json(), allowed_origins)


async def save_secrets(agent_id: str, secrets: AgentSecrets) -> None:
    pool = await connect()
    await pool.execute("UPDATE agents SET secrets = $2::jsonb, updated_at = now() WHERE id = $1",
                       agent_id, secrets.model_dump_json())


async def delete_agent(agent_id: str) -> None:
    pool = await connect()
    await pool.execute("DELETE FROM agents WHERE id = $1", agent_id)


async def start_call(session_id: str, agent_id: str, engine_agent_id: str | None = None) -> None:
    """engine_agent_id is what the Agora turns API is keyed by, and that API is the only
    per-turn latency record that outlives a call — keep it, or a bad call is unanswerable."""
    pool = await connect()
    await pool.execute(
        "INSERT INTO calls (session_id, agent_id, engine_agent_id) VALUES ($1, $2, $3)",
        session_id, agent_id, engine_agent_id)


async def end_call(session_id: str, duration_s: int, outcome: str | None,
                   lead_state: dict) -> None:
    pool = await connect()
    await pool.execute("""
        UPDATE calls SET ended_at = now(), duration_s = $2, outcome = $3, lead_state = $4::jsonb
        WHERE session_id = $1
    """, session_id, duration_s, outcome, json.dumps(lead_state))


async def agent_for_session(session_id: str) -> str | None:
    pool = await connect()
    return await pool.fetchval("SELECT agent_id FROM calls WHERE session_id = $1", session_id)


async def calls_for_agent(agent_id: str, limit: int = 50) -> list[dict]:
    pool = await connect()
    rows = await pool.fetch("""
        SELECT session_id, started_at, ended_at, duration_s, outcome, lead_state
        FROM calls WHERE agent_id = $1 ORDER BY started_at DESC LIMIT $2
    """, agent_id, limit)
    return [dict(r) for r in rows]
