"""The tool loop and its failure paths (PRD 6.3, 8).

The rule these tests protect: a bad tool call is the model's problem to recover from, and
a dead SSE stream is a dead call. Nothing in here may raise out of the proxy.
"""
import asyncio
import json

import pytest

from backend import proxy, rtm, state


def call(tool, **args):
    return {"id": f"c_{tool}", "type": "function",
            "function": {"name": tool, "arguments": json.dumps(args)}}


def scripted(*steps):
    """Feeds the tool loop one step per round trip: a tool-call list, or final text."""
    queue = list(steps)

    async def fake(config, messages, specs):
        step = queue.pop(0)
        if isinstance(step, list):
            return {"role": "assistant", "content": None, "tool_calls": step}
        return {"role": "assistant", "content": step}

    return fake


async def drain(agen):
    return [chunk async for chunk in agen]


# --- dispatch --------------------------------------------------------------------------

def test_pricing_is_answered_from_the_agents_own_knowledge(bound):
    assert proxy.run_tool(bound, "get_pricing", {"seats": 20})["tier"] == "Growth"


def test_update_lead_state_publishes_and_returns_the_new_state(bound, events):
    result = proxy.run_tool(bound, "update_lead_state", {"seat_count": 200})
    assert result["seat_count"] == 200
    assert [e["type"] for e in events] == ["lead_state", "tool_call"]


def test_every_tool_call_publishes_a_tool_call_event(bound, events):
    proxy.run_tool(bound, "get_pricing", {"seats": 20})
    published = [e for e in events if e["type"] == "tool_call"][0]
    assert published["data"]["name"] == "get_pricing"
    assert published["data"]["result_summary"] == "Growth, $39/seat"


def test_price_summaries_drop_a_pointless_decimal(bound):
    assert proxy._money(39.0) == "39"
    assert proxy._money(19.5) == "19.5"


def test_a_tool_that_raises_becomes_data_not_an_exception(bound, events):
    result = proxy.run_tool(bound, "get_pricing", {"nonsense": 1})
    assert result["error"] == "TypeError"
    assert [e for e in events if e["type"] == "tool_call"][0]["data"]["result_summary"].startswith("error:")


def test_an_unknown_tool_is_reported_not_raised(bound):
    assert "error" in proxy.run_tool(bound, "launch_missiles", {})


def test_a_disabled_tool_is_refused(bound, config):
    config.tools_enabled.calendar = False
    assert proxy.run_tool(bound, "check_slots", {})["error"] == "tool_disabled"


def test_lead_state_is_never_gated_off(bound, config):
    """Without it the agent cannot remember anything, which is the whole product."""
    for switch in ("pricing", "battlecards", "calendar", "crm", "escalation"):
        setattr(config.tools_enabled, switch, False)
    assert proxy.run_tool(bound, "update_lead_state", {"seat_count": 5})["seat_count"] == 5


def test_booking_records_the_crm_identity_key_and_the_outcome(bound, events):
    proxy.run_tool(bound, "book_meeting",
                   {"slot_iso": "2026-09-01T10:00:00+00:00", "email": "ops@acme.test"})
    assert state.get(bound)["email"] == "ops@acme.test"
    assert state.get(bound)["next_action"] == "book_demo"
    assert [e["data"]["kind"] for e in events if e["type"] == "outcome"] == ["meeting_booked"]


def test_booking_without_an_email_is_a_handled_refusal(bound, events):
    result = proxy.run_tool(bound, "book_meeting", {"slot_iso": "x", "email": ""})
    assert result["error"] == "email_required"
    assert not [e for e in events if e["type"] == "outcome"], "a failed booking is not an outcome"


def test_booking_is_idempotent_per_session(bound):
    first = proxy.run_tool(bound, "book_meeting",
                           {"slot_iso": "2026-09-01T10:00:00+00:00", "email": "a@b.test"})
    again = proxy.run_tool(bound, "book_meeting",
                           {"slot_iso": "2026-09-09T10:00:00+00:00", "email": "a@b.test"})
    assert again["already_booked"]
    assert again["slot_iso"] == first["slot_iso"]


def test_escalation_publishes_summary_and_outcome(bound, events):
    state.update(bound, company="Acme", seat_count=900)
    result = proxy.run_tool(bound, "escalate_to_human", {"reason": "asked for a human"})
    kinds = [e["type"] for e in events]
    assert "escalation" in kinds and "outcome" in kinds
    assert "Acme" in result["summary"] and "asked for a human" in result["summary"]
    assert state.get(bound)["next_action"] == "escalate"


def test_dispatch_without_a_bound_agent_is_reported_not_raised():
    """A session the proxy never saw must not take the stream down."""
    assert "error" in proxy.run_tool("sess_unknown", "get_pricing", {"seats": 10})


# --- the loop --------------------------------------------------------------------------

def test_tool_results_are_fed_back_and_the_final_text_is_returned(bound):
    proxy.complete = scripted([call("get_pricing", seats=20)], "Thirty-nine a seat.")
    assert asyncio.run(proxy.respond(bound, [{"role": "user", "content": "price?"}])) == \
        "Thirty-nine a seat."


def test_several_tools_in_one_turn_all_run(bound, events):
    proxy.complete = scripted(
        [call("update_lead_state", seat_count=200), call("get_pricing", seats=200)], "Enterprise.")
    asyncio.run(proxy.respond(bound, []))
    names = [e["data"]["name"] for e in events if e["type"] == "tool_call"]
    assert names == ["update_lead_state", "get_pricing"]


def test_malformed_tool_arguments_do_not_crash_the_turn(bound):
    broken = {"id": "c1", "type": "function",
              "function": {"name": "get_pricing", "arguments": "{not json"}}
    proxy.complete = scripted([broken], "Let me check.")
    assert asyncio.run(proxy.respond(bound, [])) == "Let me check."


def test_empty_model_text_falls_back_to_something_speakable(bound):
    proxy.complete = scripted("")
    assert asyncio.run(proxy.respond(bound, [])).strip() != ""


def test_a_model_that_only_ever_calls_tools_is_cut_off(bound):
    """Otherwise the prospect hears silence while the loop spins."""
    proxy.complete = scripted(*[[call("get_pricing", seats=10)] for _ in range(20)])
    said = asyncio.run(proxy.respond(bound, []))
    assert "colleague" in said


def test_history_is_not_mutated_by_the_loop(bound):
    history = [{"role": "user", "content": "price?"}]
    proxy.complete = scripted([call("get_pricing", seats=20)], "Done.")
    asyncio.run(proxy.respond(bound, history))
    assert history == [{"role": "user", "content": "price?"}]


# --- the stream ------------------------------------------------------------------------

def test_stream_is_valid_sse_and_terminates(bound):
    proxy.complete = scripted("Thirty nine a seat.")
    chunks = asyncio.run(drain(proxy._stream(bound, [])))
    assert chunks[-1] == "data: [DONE]\n\n"
    assert all(c.startswith("data: ") and c.endswith("\n\n") for c in chunks)


def test_streamed_words_reassemble_into_the_reply(bound):
    proxy.complete = scripted("Thirty nine a seat.")
    chunks = asyncio.run(drain(proxy._stream(bound, [])))
    text = "".join(json.loads(c[6:])["choices"][0]["delta"].get("content", "")
                   for c in chunks if c != "data: [DONE]\n\n")
    assert text.strip() == "Thirty nine a seat."


def test_the_last_chunk_carries_a_finish_reason(bound):
    proxy.complete = scripted("Hi.")
    chunks = asyncio.run(drain(proxy._stream(bound, [])))
    assert json.loads(chunks[-2][6:])["choices"][0]["finish_reason"] == "stop"


def test_a_failing_llm_still_produces_a_complete_stream(bound):
    async def explode(config, messages, specs):
        raise RuntimeError("groq is down")

    proxy.complete = explode
    chunks = asyncio.run(drain(proxy._stream(bound, [])))
    assert chunks[-1] == "data: [DONE]\n\n", "the engine must never be left hanging"


def test_a_failing_llm_still_captures_the_lead(bound):
    """PRD 11: the proxy still logs the lead and creates a follow-up task."""
    async def explode(config, messages, specs):
        raise RuntimeError("groq is down")

    proxy.complete = explode
    asyncio.run(drain(proxy._stream(bound, [])))
    assert state.get(bound)["next_action"] == "send_followup"
    assert state.get(bound)["notes"], "the failure is recorded for the rep"


@pytest.fixture(autouse=True)
def restore_complete():
    original = proxy.complete
    yield
    proxy.complete = original


def test_rebooking_does_not_announce_a_second_outcome(bound, events):
    """A live run booked once and reported meeting_booked twice, because the idempotent
    path still looked like a success."""
    args = {"slot_iso": "2026-09-01T10:00:00+00:00", "email": "a@b.test"}
    proxy.run_tool(bound, "book_meeting", args)
    proxy.run_tool(bound, "book_meeting", args)
    assert [e["data"]["kind"] for e in events if e["type"] == "outcome"] == ["meeting_booked"]


def test_escalation_speaks_the_handoff_line_through_the_engine(bound, monkeypatch):
    """PRD 19 q3: returning it as text leaves it to the model to reword or bury, and the
    rep may arrive mid-sentence. The engine speaks it directly instead."""
    from backend import agents, agora

    spoken = []

    async def fake_speak(engine_agent_id, text, interrupt=True):
        spoken.append((engine_agent_id, text, interrupt))

    monkeypatch.setattr(agora, "speak", fake_speak)
    agents.set_engine_agent(bound, "engine_1")

    async def go():
        proxy.run_tool(bound, "escalate_to_human", {"reason": "asked for a human"})
        await asyncio.sleep(0)          # let the fire-and-forget task run

    asyncio.run(go())
    assert spoken and spoken[0][0] == "engine_1"
    assert "rep" in spoken[0][1].lower()
    assert spoken[0][2] is True, "it must cut through whatever the agent is saying"


def test_escalation_survives_a_session_with_no_engine_agent(bound, events):
    """Text-mode sessions never joined a channel; the escalation must still be published."""
    proxy.run_tool(bound, "escalate_to_human", {"reason": "legal question"})
    assert [e["type"] for e in events if e["type"] == "escalation"] == ["escalation"]
