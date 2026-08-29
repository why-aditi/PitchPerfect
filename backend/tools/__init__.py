"""Tool layer. specs_for() is what the model sees; the proxy dispatches the calls.

A disabled tool is removed from the specs rather than refused after the fact. A tool the
model can still see is a tool it will still try, and then the boundary depends on prompt
discipline instead of the API (PRD 8).
"""
from . import calendar, crm, escalation  # noqa: F401  (the proxy dispatches through these)
from .battlecards import get_battlecard
from .calendar import book_meeting, check_slots
from .crm import create_deal, sync_contact
from .escalation import escalate_to_human
from .pricing import get_pricing
from ..models import AgentConfig

__all__ = ["get_pricing", "get_battlecard", "check_slots", "book_meeting", "escalate_to_human",
           "sync_contact", "create_deal", "specs_for", "SPECS"]

# Which config switch gates each tool. update_lead_state has no switch: without it the
# agent cannot remember anything, which is the whole product.
GATED_BY = {
    "get_pricing": "pricing",
    "get_battlecard": "battlecards",
    "check_slots": "calendar",
    "book_meeting": "calendar",
    "escalate_to_human": "escalation",
}

SPECS = [
    {"name": "get_pricing",
     "description": "Tier, per-seat price, volume break and features. The only source of prices.",
     "parameters": {"type": "object", "properties": {
         "tier": {"type": "string"}, "seats": {"type": "integer"}}}},
    {"name": "get_battlecard",
     "description": "Competitor positioning. Returns no_data for unknown competitors — say so, never guess.",
     "parameters": {"type": "object", "properties": {"competitor": {"type": "string"}},
                    "required": ["competitor"]}},
    {"name": "update_lead_state",
     "description": "Record anything learned about the prospect. Merges into the lead state.",
     "parameters": {"type": "object", "properties": {
         "company": {"type": "string"}, "email": {"type": "string"},
         "industry": {"type": "string"}, "use_case": {"type": "string"},
         "seat_count": {"type": "integer"},
         "budget_signal": {"type": "string", "enum": ["under_budget", "stretch", "over_budget"]},
         "timeline": {"type": "string", "enum": ["now", "this_quarter", "exploring"]},
         "objections_raised": {"type": "array", "items": {"type": "string"}},
         "competitor_mentions": {"type": "array", "items": {"type": "string"}},
         "bant": {"type": "object", "description": "0-3 per key: budget, authority, need, timeline"},
         "next_action": {"type": "string", "enum": ["book_demo", "send_followup", "escalate"]},
         "notes": {"type": "array", "items": {"type": "string"}}}}},
    {"name": "check_slots", "description": "Real calendar availability, up to 5 slots.",
     "parameters": {"type": "object", "properties": {"days_ahead": {"type": "integer"}}}},
    {"name": "book_meeting", "description": "Book the demo. Requires an email address.",
     "parameters": {"type": "object", "properties": {
         "slot_iso": {"type": "string"}, "email": {"type": "string"}, "name": {"type": "string"}},
         "required": ["slot_iso", "email"]}},
    {"name": "escalate_to_human", "description": "Hand off to a human rep on this same call.",
     "parameters": {"type": "object", "properties": {"reason": {"type": "string"}},
                    "required": ["reason"]}},
]


def specs_for(config: AgentConfig) -> list[dict]:
    """The tools this agent is allowed to call, in OpenAI function-spec shape."""
    return [s for s in SPECS
            if s["name"] not in GATED_BY
            or getattr(config.tools_enabled, GATED_BY[s["name"]])]


def enabled_names(config: AgentConfig) -> set[str]:
    return {s["name"] for s in specs_for(config)}
