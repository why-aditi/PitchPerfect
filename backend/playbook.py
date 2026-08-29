"""System prompt assembly. The proxy owns the prompt so the live lead state can be
injected every turn, and so the operator's persona edits take effect without a redeploy.

Two halves (PRD 9). The operator writes identity, goals, objection strategies and the
escalation threshold. CONSTRAINTS and CONVERSATION are fixed: they are the guarantees the
product makes, so the console must not be able to edit them away.
"""
import json

from .models import AgentConfig

CONSTRAINTS = """Hard constraints:
- Never invent a price, feature, availability date or customer name. Those come from tools only.
- If a tool returns no data, say so plainly and offer to follow up. Never estimate.
- Never offer a discount unprompted."""

CONVERSATION = """How to speak:
- Two or three sentences per turn. This is audio, not a document.
- One question at a time.
- If you were interrupted, drop the point you were making entirely. Never resume it verbatim.
- Call update_lead_state whenever you learn something, before you reply."""


def system_prompt(config: AgentConfig) -> str:
    persona = config.persona
    goals = "\n".join(f"{i}. {g}" for i, g in enumerate(persona.goal_hierarchy, 1))
    strategies = "\n".join(f"- {k.capitalize()}: {v}"
                           for k, v in persona.objection_strategies.items())
    triggers = "\n".join(f"- {t}" for t in persona.escalation_triggers)

    return f"""{persona.identity}

You are on a live voice call with a prospect. You are not reading a script.

{CONSTRAINTS}

Goal hierarchy — pursue the highest one the conversation actually supports, never force it:
{goals}

Objection strategies:
{strategies}

Escalate when:
{triggers}
- the deal is above {persona.escalation_seat_threshold} seats

{CONVERSATION}"""


def build(config: AgentConfig, state: dict, history: list[dict],
          keep_turns: int = 8) -> list[dict]:
    """System prompt + live lead state + the last N turns (older ones collapsed)."""
    system = f"{system_prompt(config)}\n\nCurrent lead state:\n{json.dumps(state, indent=2)}"
    recent = history[-keep_turns * 2:]
    older = history[:-keep_turns * 2]
    messages = [{"role": "system", "content": system}]
    if older:
        messages.append({"role": "system", "content": f"Earlier in this call: {_collapse(older)}"})
    return messages + recent


def _collapse(turns: list[dict]) -> str:
    said = [t["content"] for t in turns if t.get("role") == "user" and t.get("content")]
    return "; ".join(said)[:500] or "small talk"
