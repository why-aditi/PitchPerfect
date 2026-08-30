"""System prompt assembly. The proxy owns the prompt so the live lead state can be
injected every turn, and so the operator's persona edits take effect without a redeploy.

Two halves (PRD 9). The operator writes identity, goals, objection strategies and the
escalation threshold. CONSTRAINTS and CONVERSATION are fixed: they are the guarantees the
product makes, so the console must not be able to edit them away.
"""
import json

from .models import AgentConfig

CONSTRAINTS = """Rules:
- Prices, features, dates and customer names come from tools only. Never invent one.
- No data from a tool means say so and offer to follow up. Never estimate.
- Never discount unprompted."""

CONVERSATION = """Speaking:
- Two or three sentences. This is audio.
- One question at a time.
- If interrupted, drop that point entirely. Never resume it.
- Call update_lead_state as soon as you learn something, before replying."""


def system_prompt(config: AgentConfig) -> str:
    persona = config.persona
    # Lists are joined inline rather than bulleted: this whole string is resent on every
    # request, so the scaffolding around the operator's words is worth keeping thin.
    goals = " > ".join(persona.goal_hierarchy)
    strategies = "\n".join(f"- {k.capitalize()}: {v}"
                           for k, v in persona.objection_strategies.items())
    triggers = "; ".join(persona.escalation_triggers)

    return f"""{persona.identity}

You are on a live voice call with a prospect. There is no script.

{CONSTRAINTS}

Goals, highest first — pursue the highest the conversation supports, never force it:
{goals}

Objections:
{strategies}

Escalate when: {triggers}; or the deal is above {persona.escalation_seat_threshold} seats

{CONVERSATION}"""


def compact_state(state: dict) -> str:
    """Only what has actually been learned, on one line.

    The lead state goes out on every request, so an indented dump of mostly nulls is the
    cheapest thing to cut on a token budget. What fields exist is the tool schema's job to
    say; this is the value, not the shape. bant and qualification always ride along because
    they drive the goal the agent pursues.
    """
    keep = {k: v for k, v in state.items()
            if v not in (None, [], "") and k != "session_id"}
    return json.dumps(keep, separators=(",", ":"))


def build(config: AgentConfig, state: dict, history: list[dict],
          keep_turns: int = 8) -> list[dict]:
    """System prompt + live lead state + the last N turns (older ones collapsed)."""
    system = f"{system_prompt(config)}\n\nLead state so far: {compact_state(state)}"
    recent = history[-keep_turns * 2:]
    older = history[:-keep_turns * 2]
    messages = [{"role": "system", "content": system}]
    if older:
        messages.append({"role": "system", "content": f"Earlier in this call: {_collapse(older)}"})
    return messages + recent


def _collapse(turns: list[dict]) -> str:
    said = [t["content"] for t in turns if t.get("role") == "user" and t.get("content")]
    return "; ".join(said)[:500] or "small talk"
