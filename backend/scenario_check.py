"""Phase 2 gate: the PRD section 14 acceptance scenario, in text, with no API keys.

The LLM is scripted so this asserts OUR logic — tool dispatch, lead-state merges,
BANT derivation, the events the dashboard renders — not Groq's word choice. Run:

    python -m backend.scenario_check
"""
import asyncio
import json

from . import agents, proxy, rtm, state, tools
from .models import AgentSecrets
from .seed import DEMO_ID, demo_config

SID = "sess_test"
events: list[dict] = []

EXPECT_TOOLS = ["get_pricing", "get_battlecard", "update_lead_state",
                "check_slots", "book_meeting", "cancel_meeting", "escalate_to_human"]


def _call(tool, **args):
    return {"id": f"c_{tool}", "type": "function",
            "function": {"name": tool, "arguments": json.dumps(args)}}


# One entry per LLM round trip: tool calls first, then the text the agent speaks.
SCRIPT = [
    # 1. "What's the price for about 20 users?"
    [_call("update_lead_state", seat_count=20, bant={"need": 2}), _call("get_pricing", seats=20)],
    "Growth works out at thirty-nine dollars per seat per month for twenty people.",
    # 2. interrupted mid-answer: "how does that compare to Northbeam?"
    [_call("update_lead_state", competitor_mentions=["Northbeam"]), _call("get_battlecard", competitor="Northbeam")],
    "Their attribution modelling is deeper. We win on setup time and workflow automation.",
    # 3. "Actually it'd be closer to 200 users."
    [_call("update_lead_state", seat_count=200, bant={"authority": 2}), _call("get_pricing", seats=200)],
    "At two hundred seats you move to Enterprise, thirty-two dollars a seat.",
    # 4. "That's a lot more than we budgeted."
    [_call("update_lead_state", objections_raised=["pricing"], budget_signal="over_budget")],
    "Per seat it is actually lower than the Growth rate. Would a paid pilot on one team help?",
    # 5. "Can we see an enterprise demo?"
    [_call("check_slots", days_ahead=5)],
    "I have Tuesday at ten or Wednesday at three UTC.",
    [_call("book_meeting", slot_iso="2026-09-01T10:00:00+00:00", email="ops@acme.test", name="Acme"),
     _call("update_lead_state", company="Acme", timeline="this_quarter", bant={"budget": 2, "timeline": 3})],
    "Booked for Tuesday at ten. Confirmation is on its way to ops@acme.test.",
]


async def fake_complete(config, messages, specs):
    """Replaces the Groq round trip. Returns scripted tool calls, then scripted text."""
    assert {s["name"] for s in specs} == set(EXPECT_TOOLS), "the agent must offer exactly its enabled tools"
    step = SCRIPT.pop(0)
    if isinstance(step, list):
        return {"role": "assistant", "content": None, "tool_calls": step}
    return {"role": "assistant", "content": step}


async def main():
    rtm.subscribe(events.append)
    proxy.complete = fake_complete

    # The whole point of Phase 2: config comes from an agent record, not from module
    # constants. The record is built here rather than fetched, so this stays a text-mode
    # gate that needs no database — tests/test_db.py covers the Postgres path itself.
    config = demo_config()
    agents._bound[SID] = (DEMO_ID, config, AgentSecrets())
    assert config.knowledge.tiers, "the agent carries its own pricing"

    history = []
    for prompt in ["Price for about 20 users?", "How does that compare to Northbeam?",
                   "Actually it'd be closer to 200 users.", "That's a lot more than we budgeted.",
                   "Can we see an enterprise demo?", "Tuesday at ten, ops@acme.test."]:
        history.append({"role": "user", "content": prompt})
        said = await proxy.respond(SID, history)
        history.append({"role": "assistant", "content": said})
        print(f"  prospect: {prompt}\n     agent: {said}\n")

    lead = state.get(SID)
    kinds = [e["type"] for e in events]
    called = [e["data"]["name"] for e in events if e["type"] == "tool_call"]
    quotes = [e["data"]["result_summary"] for e in events
              if e["type"] == "tool_call" and e["data"]["name"] == "get_pricing"]

    # Step 3 is the gate: the seat change must re-quote without being asked again.
    assert quotes == ["Growth, $39/seat", "Enterprise, $32/seat"], quotes
    assert lead["seat_count"] == 200, lead["seat_count"]
    assert lead["company"] == "Acme"
    assert lead["email"] == "ops@acme.test", "booking must record the CRM identity key"
    assert lead["objections_raised"] == ["pricing"], lead["objections_raised"]
    assert lead["competitor_mentions"] == ["Northbeam"], lead["competitor_mentions"]
    assert lead["budget_signal"] == "over_budget"
    # The model scored budget 2, authority 2, need 2, timeline 3. need is floored up to 3
    # because a competitor was named and a seat count is known, which is an active
    # evaluation. 2+2+3+3 = 10 -> hot. qualification is always derived, never model-set.
    assert lead["bant"] == {"budget": 2, "authority": 2, "need": 3, "timeline": 3}, lead["bant"]
    assert lead["qualification"] == "hot", lead["qualification"]
    assert lead["next_action"] == "book_demo", lead["next_action"]

    assert called.count("get_battlecard") == 1 and called.count("check_slots") == 1
    assert "book_meeting" in called
    outcomes = [e["data"]["kind"] for e in events if e["type"] == "outcome"]
    assert outcomes == ["meeting_booked"], outcomes
    assert kinds.count("lead_state") >= 6, kinds

    # Booking is idempotent per session (PRD 8): the same slot twice is one meeting.
    booked_iso = [e["data"]["detail"]["slot_iso"] for e in events
                  if e["type"] == "outcome" and e["data"]["kind"] == "meeting_booked"][0]
    again = proxy.run_tool(SID, "book_meeting",
                           {"slot_iso": booked_iso, "email": "ops@acme.test", "name": "Acme"}, history)
    assert again.get("already_booked") and again["slot_iso"] == booked_iso, again

    # A different slot is not a second meeting either — it is the same one, moved. Refusing
    # here is what "actually, can we do Wednesday?" used to sound like on a live call. The
    # settle window has to be stepped past: seconds after booking, a new slot is the model
    # repeating itself, and honouring it emails the prospect twice about one demo.
    from .tools import calendar as _cal
    _cal._booked[SID]["booked_at"] -= _cal.SETTLE_S + 1
    # Seconds after booking, a new slot is the model repeating itself rather than the
    # prospect moving the meeting; the settle window has to be stepped past deliberately.
    from .tools import calendar as _cal
    _cal._booked[SID]["booked_at"] -= _cal.SETTLE_S + 1
    moved = proxy.run_tool(SID, "book_meeting",
                           {"slot_iso": "2026-09-02T10:00:00+00:00", "email": "ops@acme.test", "name": "Acme"},
                           history)
    assert moved["slot_iso"].startswith("2026-09-02"), moved
    assert moved["rescheduled_from"] == booked_iso, moved
    assert moved["booking_id"] == again["booking_id"], "moving must not open a second booking"

    # A tool the model calls wrongly must come back as data, not a 500.
    bad = proxy.run_tool(SID, "get_battlecard", {"competitor": "NobodyCorp"})
    assert bad["error"] == "no_data", bad
    assert proxy.run_tool(SID, "get_pricing", {"nonsense": 1})["error"] == "TypeError"

    # A tool switched off in the console is not offered, and is refused if asked for anyway.
    config.tools_enabled.calendar = False
    assert "check_slots" not in {s["name"] for s in tools.specs_for(config)}
    assert proxy.run_tool(SID, "check_slots", {})["error"] == "tool_disabled"
    config.tools_enabled.calendar = True

    # The origin allowlist lives in tests/test_api.py, which stubs the agent lookup. It
    # needs a database here now that /start-call no longer falls back to the seed, and
    # this gate is about the conversation, not the HTTP surface.

    print(f"scenario_check ok — {len(events)} events, lead is {lead['qualification']}")


if __name__ == "__main__":
    asyncio.run(main())
