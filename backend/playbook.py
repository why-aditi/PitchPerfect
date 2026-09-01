"""System prompt assembly. The proxy owns the prompt so the live lead state can be
injected every turn, and so the operator's persona edits take effect without a redeploy.

Two halves (PRD 9). The operator writes identity, goals, objection strategies and the
escalation threshold. CONSTRAINTS and CONVERSATION are fixed: they are the guarantees the
product makes, so the console must not be able to edit them away.
"""
import json
from datetime import datetime, timezone

from .models import AgentConfig

CONSTRAINTS = """Rules:
- Prices, features, dates and customer names come from tools only. Never invent one.
- No data from a tool means say so and offer to follow up. Never estimate.
- Never discount unprompted."""

# Every line here earns its tokens by removing a specific tell. Models default to written
# prose, and written prose read aloud is what makes an agent sound like an agent: the
# preamble before the answer, the three-item list, the read-back confirmation, the raw
# timestamp. Naming each one is cheaper than hoping "be conversational" covers it.
CONVERSATION = """Speaking — a phone call, not chat:
- One or two sentences, then stop. Three is a monologue.
- Contractions. I'll, you're, that's, we've.
- Answer first. No "Great question", no "Absolutely", no "I'd be happy to".
- React in one word if it helps — "Right." "Got it." — then move on.
- Never list. Say the one that matters and let them ask for the rest.
- Never read their words back to confirm you heard them.
- Say times like a person: "Thursday at ten", never a date or a raw timestamp.
- Prices: read the tool's "spoken" field as written. Never spell a number into words
  and never do the arithmetic yourself — a live call turned $780 into "seventy-eight".
- One question at a time, and only when you need the answer.
- Before booking, get their name and their email. Ask for the name first, then the
  email, and read the email back before you book it.
- If interrupted, drop that point entirely. Never resume it.
- Silence is fine. Do not fill it by restating.
- Call update_lead_state the moment anything lands — company, seats, industry, use
  case, budget, timeline, an objection, a competitor — before you reply, every time.
- Find out their budget and their timeline. Qualification depends on both."""


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
    """Stable prompt, then the volatile block, then the last N turns.

    The split is the whole point, and it is about cost rather than wording. Groq caches
    on a matching prefix and cached tokens do not count against tokens-per-minute, so
    everything constant has to sit in front of everything that moves. Folding the clock
    and the lead state into the persona message put a per-minute timestamp at the very
    front and invalidated the prefix on every request — including the tool specs, which
    are the larger half of the ~1200 tokens this pays for.

    The clock itself is not optional: without it the model cannot resolve "tomorrow"
    against the ISO slots check_slots returns, and reads the timestamp aloud instead.
    """
    now = datetime.now(timezone.utc).strftime("%A %d %B %Y, %H:%M UTC")
    recent = history[-keep_turns * 2:]
    older = history[:-keep_turns * 2]

    # Byte-identical on every request for a given agent. Nothing may be added here.
    messages = [{"role": "system", "content": system_prompt(config)}]
    volatile = f"Right now it is {now}." + "\n" + f"Lead state so far: {compact_state(state)}"
    if older:
        volatile += "\n" + f"Earlier in this call: {_collapse(older)}"
    messages.append({"role": "system", "content": volatile})
    return messages + recent


def _collapse(turns: list[dict]) -> str:
    said = [t["content"] for t in turns if t.get("role") == "user" and t.get("content")]
    return "; ".join(said)[:500] or "small talk"
