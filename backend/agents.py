"""Resolves which agent a call belongs to, and caches its config for the call's life.

Config is read on every turn. A free-tier Postgres cold start in the tool path would
land directly on turn latency, so a call loads its agent once at /start-call and reads
from memory after that (PRD 11). Editing an agent therefore takes effect on the next
call, not mid-call, which is also the behaviour the console promises.
"""
from . import db
from .models import AgentConfig, AgentSecrets

_bound: dict[str, tuple[str, AgentConfig, AgentSecrets]] = {}
_engine: dict[str, str] = {}   # session_id -> the engine's own agent id, for speak/leave
_timezone: dict[str, str] = {}  # session_id -> the prospect's IANA zone, from their browser


async def load(agent_id: str) -> tuple[AgentConfig, AgentSecrets] | None:
    """Read an agent from the database. Returns None if it does not exist."""
    agent = await db.get_agent(agent_id)
    if agent is None:
        return None
    return agent["config"], await db.get_secrets(agent_id)


async def bind(session_id: str, agent_id: str) -> tuple[AgentConfig, AgentSecrets] | None:
    """Pin an agent's config to a session for the duration of the call."""
    loaded = await load(agent_id)
    if loaded is None:
        return None
    _bound[session_id] = (agent_id, *loaded)
    return loaded


def bind_record(session_id: str, agent_id: str, config: AgentConfig,
                secrets: AgentSecrets) -> None:
    """Pin a record the caller has already read. bind() re-reads; /start-call must not."""
    _bound[session_id] = (agent_id, config, secrets)


def for_session(session_id: str) -> tuple[str, AgentConfig, AgentSecrets] | None:
    return _bound.get(session_id)


def set_engine_agent(session_id: str, engine_agent_id: str) -> None:
    _engine[session_id] = engine_agent_id


def engine_agent(session_id: str) -> str | None:
    return _engine.get(session_id)


def set_timezone(session_id: str, name: str | None) -> None:
    """The prospect's own zone, as the browser reports it at /start-call."""
    if name:
        _timezone[session_id] = name


def timezone_for(session_id: str) -> str | None:
    return _timezone.get(session_id)


def sessions_for(agent_id: str) -> list[str]:
    """Calls currently in progress for this agent."""
    return [sid for sid, (aid, _, _) in _bound.items() if aid == agent_id]


def release(session_id: str) -> None:
    _bound.pop(session_id, None)
    _engine.pop(session_id, None)


def allowed_origin(origins: list[str], origin: str | None) -> bool:
    """Agent ids are public — they sit in the embed snippet — so this is what stops a
    stranger starting calls on someone else's agent (PRD 6.1)."""
    if not origins:
        return False  # an agent with no origins configured is not embeddable yet
    return origin is not None and origin.rstrip("/") in {o.rstrip("/") for o in origins}
