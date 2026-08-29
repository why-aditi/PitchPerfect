"""Tool layer. SPECS is what the LLM sees; REGISTRY is what the proxy calls."""
from .pricing import get_pricing
from .battlecards import get_battlecard
from .crm import sync_contact
from .calendar import check_slots, book_meeting
from .escalation import escalate_to_human

REGISTRY = {
    "get_pricing": get_pricing,
    "get_battlecard": get_battlecard,
    "check_slots": check_slots,
    "book_meeting": book_meeting,
    "escalate_to_human": escalate_to_human,
}

# update_lead_state is bound per-session by the proxy, so it is not in REGISTRY.

SPECS = [
    {"name": "get_pricing", "description": "Tier, per-seat price, volume break and features. The only source of prices.",
     "parameters": {"type": "object", "properties": {
         "tier": {"type": "string"}, "seats": {"type": "integer"}}}},
    {"name": "get_battlecard", "description": "Competitor positioning. Returns no_data for unknown competitors — say so, never guess.",
     "parameters": {"type": "object", "properties": {"competitor": {"type": "string"}}, "required": ["competitor"]}},
    {"name": "update_lead_state", "description": "Record anything learned about the prospect. Merges into the lead state.",
     "parameters": {"type": "object", "properties": {
         "company": {"type": "string"}, "industry": {"type": "string"}, "use_case": {"type": "string"},
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
     "parameters": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}},
]
