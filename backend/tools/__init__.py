"""Tool layer. specs_for() is what the model sees; the proxy dispatches the calls.

A disabled tool is removed from the specs rather than refused after the fact. A tool the
model can still see is a tool it will still try, and then the boundary depends on prompt
discipline instead of the API (PRD 8).
"""
from . import calendar, crm, escalation  # noqa: F401  (the proxy dispatches through these)
from .battlecards import get_battlecard
from .calendar import (book_meeting, cancel_meeting, check_slots, clean_email,
                       was_actually_said)
from .crm import create_deal, sync_contact
from .escalation import escalate_to_human
from .pricing import get_pricing
from ..models import AgentConfig

__all__ = ["get_pricing", "get_battlecard", "check_slots", "book_meeting",
           "cancel_meeting", "escalate_to_human",
           "sync_contact", "create_deal", "clean_email", "was_actually_said",
           "specs_for", "SPECS", "LEAD_STATE_SPEC"]

# Which config switch gates each tool. update_lead_state has no switch: without it the
# agent cannot remember anything, which is the whole product.
GATED_BY = {
    "get_pricing": "pricing",
    "get_battlecard": "battlecards",
    "check_slots": "calendar",
    "book_meeting": "calendar",
    "cancel_meeting": "calendar",
    "escalate_to_human": "escalation",
}

def _nullable(spec: dict) -> dict:
    """Let every optional field accept null.

    Models emit `"company": null` for fields they have nothing to say about, and Groq's
    tool-call validator rejects that against `type: "string"` with a 400 — which fails the
    whole turn, so the prospect hears the fallback line for a tool call that was fine.
    Every optional field here is optional precisely because null and absent mean the same
    thing, and state.update drops both. Required fields are left strict on purpose.
    """
    params = spec.get("parameters", {})
    required = set(params.get("required", []))
    for name, prop in params.get("properties", {}).items():
        if name in required:
            continue
        if "enum" in prop:
            prop["enum"] = [*prop["enum"], None]
        elif isinstance(prop.get("type"), str):
            prop["type"] = [prop["type"], "null"]
    return spec


SPECS = [_nullable(s) for s in [
    # Descriptions are terse on purpose: the whole block is resent on every request and is
    # the largest part of the payload. Each keeps the one phrase that decides when the tool
    # applies, and update_lead_state keeps its enums, which constrain the values we store.
    {"name": "get_pricing",
     "description": "Tier, per-seat price, volume break, features. The only source of prices.",
     "parameters": {"type": "object", "properties": {
         "tier": {"type": "string"}, "seats": {"type": "integer"}}}},
    {"name": "get_battlecard",
     "description": "Competitor positioning. Returns no_data for unknown ones — say so, never guess.",
     "parameters": {"type": "object", "properties": {"competitor": {"type": "string"}},
                    "required": ["competitor"]}},
    {"name": "check_slots",
     "description": "Real availability, up to 5 slots. Offer two of them, never the list.",
     "parameters": {"type": "object", "properties": {
         "days_ahead": {"type": "integer"},
         "timezone_name": {"type": "string",
                           "description": "Their timezone, however they said it: "
                                          "'Eastern', 'PST', 'Europe/Berlin'. Ask if unsaid."}}}},
    {"name": "book_meeting",
     "description": "Book the demo, or move it if one is already booked. Needs a name AND "
                    "an email — ask for both before calling this.",
     "parameters": {"type": "object", "properties": {
         "slot_iso": {"type": "string", "description": "Exactly the iso from check_slots."},
         "email": {"type": "string", "description": "As they said it; spoken form is fine."},
         "name": {"type": "string", "description": "Who the invite is for, as they gave it. "
                                                   "Never taken from the email address."},
         "timezone_name": {"type": "string"}},
         "required": ["slot_iso", "email", "name"]}},
    {"name": "cancel_meeting",
     "description": "Call off the demo booked on THIS call. Cannot touch any other booking.",
     "parameters": {"type": "object", "properties": {
         "reason": {"type": "string", "description": "What they said, briefly."}}}},
    {"name": "escalate_to_human", "description": "Hand off to a human rep on this call.",
     "parameters": {"type": "object", "properties": {"reason": {"type": "string"}},
                    "required": ["reason"]}},
]]


# Not offered to the speaking model. Lead capture runs beside the reply in extract.py,
# where a second model is forced to call this after every turn; putting it in front of
# the reply made every turn two round trips. The dispatch still accepts it from anywhere.
LEAD_STATE_SPEC = _nullable(
    {"name": "update_lead_state",
     "description": "Record anything learned about the prospect. Merges.",
     "parameters": {"type": "object", "properties": {
         "company": {"type": "string"}, "email": {"type": "string"},
         "industry": {"type": "string"}, "use_case": {"type": "string"},
         "seat_count": {"type": "integer"},
         # Named from our price's point of view, which a model will otherwise read the
         # other way round: a live run recorded "we budgeted less than that" as under_budget.
         "budget_signal": {"enum": ["under_budget", "stretch", "over_budget"],
                           "description": "our price vs their budget: under_budget fits, "
                                          "stretch is tight, over_budget is too expensive"},
         "timeline": {"enum": ["now", "this_quarter", "exploring"]},
         "objections_raised": {"type": "array", "items": {"type": "string"}},
         "competitor_mentions": {"type": "array", "items": {"type": "string"}},
         "bant": {"type": "object", "description": "0-3 each: budget, authority, need, timeline"},
         "next_action": {"enum": ["book_demo", "send_followup", "escalate"]},
         "notes": {"type": "array", "items": {"type": "string"}}}}})


def specs_for(config: AgentConfig) -> list[dict]:
    """The tools this agent is allowed to call, in OpenAI function-spec shape."""
    return [s for s in SPECS
            if s["name"] not in GATED_BY
            or getattr(config.tools_enabled, GATED_BY[s["name"]])]


def enabled_names(config: AgentConfig) -> set[str]:
    return {s["name"] for s in specs_for(config)}
