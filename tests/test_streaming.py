"""The streamed turn (PRD 6.3, 15.1 turn latency).

The engine starts TTS on the first complete sentence it receives, so the proxy has to
forward text as the LLM produces it. Buffering the whole answer and then chunking it
word by word — what the proxy did until 2026-09-03 — put the full generation time in
front of the first audio on every turn.
"""
import asyncio
import json

import pytest

from backend import extract, proxy, state, tools


def sse(*objs):
    """Upstream SSE bytes, one chunk per object, terminated like a real provider."""
    return "".join(f"data: {json.dumps(o)}\n\n" for o in objs) + "data: [DONE]\n\n"


def delta(content=None, tool_calls=None, finish=None):
    d = {}
    if content is not None:
        d["content"] = content
    if tool_calls is not None:
        d["tool_calls"] = tool_calls
    return {"choices": [{"index": 0, "delta": d, "finish_reason": finish}]}


async def collect(agen):
    return [x async for x in agen]


# --- parsing the upstream stream ---------------------------------------------------------

def test_text_deltas_are_forwarded_as_they_arrive_and_reassembled():
    lines = sse(delta("Thirty-"), delta("nine "), delta("a seat."), delta(finish="stop")).splitlines()
    events = asyncio.run(collect(proxy._parse_sse(_aiter(lines))))
    texts = [e[1] for e in events if e[0] == "text"]
    assert texts == ["Thirty-", "nine ", "a seat."]
    final = [e[1] for e in events if e[0] == "message"][0]
    assert final["content"] == "Thirty-nine a seat."
    assert not final.get("tool_calls")


def test_tool_call_deltas_are_accumulated_by_index():
    """Mistral sends the arguments in pieces; OpenAI-style providers send a name first and
    then argument fragments. Both have to end up as one call with parseable arguments."""
    lines = sse(
        delta(tool_calls=[{"index": 0, "id": "c1", "type": "function",
                           "function": {"name": "get_pricing", "arguments": ""}}]),
        delta(tool_calls=[{"index": 0, "function": {"arguments": '{"seats": '}}]),
        delta(tool_calls=[{"index": 0, "function": {"arguments": "20}"}}]),
        delta(tool_calls=[{"index": 1, "id": "c2", "type": "function",
                           "function": {"name": "get_battlecard",
                                        "arguments": '{"competitor": "Northbeam"}'}}]),
        delta(finish="tool_calls"),
    ).splitlines()
    events = asyncio.run(collect(proxy._parse_sse(_aiter(lines))))
    final = [e[1] for e in events if e[0] == "message"][0]
    calls = final["tool_calls"]
    assert [c["function"]["name"] for c in calls] == ["get_pricing", "get_battlecard"]
    assert json.loads(calls[0]["function"]["arguments"]) == {"seats": 20}
    assert calls[0]["id"] == "c1" and calls[1]["id"] == "c2"
    assert not [e for e in events if e[0] == "text"], "a tool turn speaks nothing yet"


def test_a_stream_with_no_done_marker_still_yields_the_message():
    lines = sse(delta("Hi."))[:-len("data: [DONE]\n\n")].splitlines()
    events = asyncio.run(collect(proxy._parse_sse(_aiter(lines))))
    assert [e[1] for e in events if e[0] == "message"][0]["content"] == "Hi."


def test_malformed_lines_are_skipped_not_fatal():
    lines = ["data: {not json", ": keepalive", "", "data: " + json.dumps(delta("Ok.")), "data: [DONE]"]
    events = asyncio.run(collect(proxy._parse_sse(_aiter(lines))))
    assert [e[1] for e in events if e[0] == "message"][0]["content"] == "Ok."


# --- the streamed turn ---------------------------------------------------------------------

def scripted(*steps):
    """Like tests/test_proxy.scripted, but streams the text through the sink word by word
    the way the real upstream does, so ordering can be asserted."""
    queue = list(steps)

    async def fake(config, messages, specs, sink=None, **kw):
        step = queue.pop(0)
        if isinstance(step, list):
            return {"role": "assistant", "content": None, "tool_calls": step}
        if sink is not None:
            for word in step.split(" "):
                await sink(word + " ")
        return {"role": "assistant", "content": step}

    return fake


def call(tool, **args):
    return {"id": f"c_{tool}", "type": "function",
            "function": {"name": tool, "arguments": json.dumps(args)}}


@pytest.fixture(autouse=True)
def restore():
    original = proxy.complete
    yield
    proxy.complete = original


def test_streamed_pieces_arrive_before_the_turn_finishes(bound):
    proxy.complete = scripted("Thirty nine a seat.")
    pieces = asyncio.run(collect(proxy.stream_turn(bound, [{"role": "user", "content": "price?"}])))
    assert "".join(pieces).strip() == "Thirty nine a seat."
    assert len(pieces) > 1, "one piece means the whole answer was buffered"


def test_a_tool_hop_then_text_streams_the_text(bound):
    proxy.complete = scripted([call("get_pricing", seats=20)], "Thirty-nine a seat.")
    pieces = asyncio.run(collect(proxy.stream_turn(bound, [{"role": "user", "content": "price?"}])))
    assert "".join(pieces).strip() == "Thirty-nine a seat."


def test_a_fake_that_does_not_stream_still_produces_the_reply(bound):
    """A complete() that only returns the message (the scripted fakes elsewhere) must not
    leave the engine with an empty stream."""
    async def whole(config, messages, specs, **kw):
        return {"role": "assistant", "content": "All at once."}

    proxy.complete = whole
    pieces = asyncio.run(collect(proxy.stream_turn(bound, [])))
    assert "".join(pieces).strip() == "All at once."


def test_the_sse_stream_carries_the_streamed_text_in_order(bound):
    proxy.complete = scripted("One two three.")
    chunks = asyncio.run(collect(proxy._stream(bound, [])))
    text = "".join(json.loads(c[6:])["choices"][0]["delta"].get("content", "")
                   for c in chunks if c != "data: [DONE]\n\n")
    assert text.strip() == "One two three."
    assert chunks[-1] == "data: [DONE]\n\n"
    assert json.loads(chunks[-2][6:])["choices"][0]["finish_reason"] == "stop"


def test_an_unbound_session_is_a_404_not_a_spoken_apology():
    """The wrong backend answering 200 with an apology is exactly what hid the tunnel bug.
    A session this process never started is an error the engine should see as one."""
    from fastapi.testclient import TestClient
    from backend import main

    r = TestClient(main.app).post("/v1/chat/completions?session_id=sess_stranger",
                                  json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 404


def test_tools_run_off_the_event_loop(bound, monkeypatch):
    """Cal.com and HubSpot are called with a blocking client. Run on the loop, a slow
    booking stalls every other call's turn; run in a thread it stalls only its own."""
    import threading
    seen = {}

    def spy(sid, name, args, history=None):
        seen["thread"] = threading.current_thread().name
        return {"tier": "Growth"}

    monkeypatch.setattr(proxy, "run_tool", spy)
    proxy.complete = scripted([call("get_pricing", seats=20)], "Done.")
    asyncio.run(collect(proxy.stream_turn(bound, [])))
    assert seen["thread"] != threading.main_thread().name


# --- lead extraction off the critical path ------------------------------------------------

def test_the_speaking_model_is_not_offered_update_lead_state(config):
    """Every turn used to be two LLM round trips because the prompt demanded a lead-state
    call before the reply. Capture now runs beside the reply, not in front of it."""
    assert "update_lead_state" not in {s["name"] for s in tools.specs_for(config)}
    assert tools.LEAD_STATE_SPEC["name"] == "update_lead_state"


def test_extraction_merges_into_the_lead_state_and_publishes(bound, events, monkeypatch):
    async def fake_complete(config, messages, specs, **kw):
        assert [s["name"] for s in specs] == ["update_lead_state"]
        assert kw.get("tool_choice"), "the extractor must be forced to call the tool"
        return {"role": "assistant", "content": None,
                "tool_calls": [call("update_lead_state", company="Acme", seat_count=40)]}

    monkeypatch.setattr(proxy, "complete", fake_complete)
    history = [{"role": "user", "content": "we're Acme, about forty people"},
               {"role": "assistant", "content": "Got it."}]
    asyncio.run(extract.run(bound, history))
    assert state.get(bound)["company"] == "Acme"
    assert state.get(bound)["seat_count"] == 40
    assert "lead_state" in [e["type"] for e in events]


def test_extraction_failures_never_surface(bound, monkeypatch):
    async def explode(config, messages, specs, **kw):
        raise RuntimeError("provider down")

    monkeypatch.setattr(proxy, "complete", explode)
    asyncio.run(extract.run(bound, [{"role": "user", "content": "hi"}]))   # must not raise
    assert state.get(bound)["company"] is None


def test_overlapping_extractions_coalesce_to_the_latest_history(bound, monkeypatch):
    """Turns can finish faster than extraction runs. One extractor per session, and it
    always sees the newest transcript rather than queueing a run per turn."""
    ran = []
    gate = asyncio.Event()

    async def slow(config, messages, specs, **kw):
        ran.append(messages[-1]["content"])
        await gate.wait()
        return {"role": "assistant", "content": None, "tool_calls": []}

    monkeypatch.setattr(proxy, "complete", slow)

    async def go():
        extract.schedule(bound, [{"role": "user", "content": "one"}])
        await asyncio.sleep(0)
        extract.schedule(bound, [{"role": "user", "content": "two"}])
        extract.schedule(bound, [{"role": "user", "content": "three"}])
        gate.set()
        await extract.drain(bound)

    asyncio.run(go())
    assert len(ran) == 2, "the second and third requests collapsed into one run"
    assert "three" in ran[-1]
    assert "two" not in ran[-1] or "three" in ran[-1]


def test_stop_call_waits_for_the_last_extraction(bound, monkeypatch):
    """Whatever the prospect said in the final turn still has to reach the CRM."""
    done = asyncio.Event()

    async def late(config, messages, specs, **kw):
        await asyncio.sleep(0.05)
        done.set()
        return {"role": "assistant", "content": None,
                "tool_calls": [call("update_lead_state", company="Late Co")]}

    monkeypatch.setattr(proxy, "complete", late)

    async def go():
        extract.schedule(bound, [{"role": "user", "content": "we are Late Co"}])
        await extract.drain(bound)

    asyncio.run(go())
    assert done.is_set()
    assert state.get(bound)["company"] == "Late Co"


async def _aiter(lines):
    for line in lines:
        yield line
