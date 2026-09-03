"""The concession ladder.

The property under test is not "a tool returns a string". It is that everything the agent
commits to on a call came from the operator's config, one rung at a time, with an ask
attached — and that when the config runs out the answer is a human rather than a better
price. Those are the four things that make this negotiation rather than caving.
"""
import pytest

from backend import proxy, state
from backend.models import Concession, Knowledge, Persona, AgentConfig
from backend.tools.negotiation import propose_concession

LADDER = [
    Concession(give="a thirty-day pilot", require="an exec sponsor and a decision date"),
    Concession(give="onboarding included", require="a twelve-month commit", min_seats=50),
    Concession(give="annual prepay terms", require="paperwork inside the quarter"),
]


@pytest.fixture
def agent(config):
    return config.model_copy(update={
        "knowledge": config.knowledge.model_copy(update={"concessions": list(LADDER)})})


def test_the_first_push_gets_the_cheapest_rung(agent):
    """The list is the ladder. An agent that opens with its best offer has nothing left."""
    result = propose_concession(agent, offered=[], seats=200)
    assert result["give"] == "a thirty-day pilot"
    assert result["remaining"] == 2


def test_every_concession_arrives_with_its_ask(agent):
    """A concession with nothing asked in return is a discount with extra steps."""
    result = propose_concession(agent, offered=[], seats=200)
    assert result["require"] == "an exec sponsor and a decision date"
    assert result["spoken"] == ("What I can do is a thirty-day pilot — if an exec sponsor "
                                "and a decision date.")


def test_a_second_push_gets_a_different_rung(agent):
    """The failure this prevents is the agent repeating its last offer, louder."""
    first = propose_concession(agent, offered=[], seats=200)
    second = propose_concession(agent, offered=[first["give"]], seats=200)
    assert second["give"] == "onboarding included"


def test_only_one_thing_is_ever_offered_at_a_time(agent):
    """A model handed a list will read the list, and then the whole ladder is spent on
    one turn for nothing in return."""
    result = propose_concession(agent, offered=[], seats=200)
    assert "onboarding included" not in str(result)
    assert "do not offer the next thing" in result["instruction"]


def test_a_rung_the_seat_count_cannot_justify_is_skipped(agent):
    """Included onboarding on a ten-seat deal costs more than the deal."""
    result = propose_concession(agent, offered=["a thirty-day pilot"], seats=10)
    assert result["give"] == "annual prepay terms", "the 50-seat rung must be stepped over"


def test_an_unknown_seat_count_does_not_make_the_agent_stubborn(agent):
    """Refusing to concede because nobody has said a number yet is the wrong failure."""
    assert propose_concession(agent, offered=[], seats=None)["give"] == "a thirty-day pilot"


def test_the_end_of_the_ladder_is_a_human_not_a_discount(agent):
    """The whole point. When there is nothing left to trade the agent must not improvise
    one, and must not quietly repeat itself either."""
    spent = [c.give for c in LADDER]
    result = propose_concession(agent, offered=spent, seats=200)
    assert result["error"] == "at_limit"
    assert "do not invent a discount" in result["instruction"].lower()
    assert "colleague" in result["instruction"]


def test_an_agent_with_no_ladder_holds_the_price(config):
    """An operator who configured nothing has authorised nothing. The agent still needs a
    reply that is not silence and is not a made-up offer."""
    result = propose_concession(config, offered=[], seats=200)
    assert result["error"] == "no_data"
    assert "Hold the price" in result["instruction"]


# --- through the dispatcher --------------------------------------------------------------

def test_what_was_given_is_recorded_by_the_dispatcher_not_the_model(bound, agent,
                                                                    monkeypatch, events):
    """The record of what a call committed to has to come from what a tool actually
    produced. A model asked to remember its own concessions will lose one under pressure."""
    monkeypatch.setattr(proxy, "_bound", lambda sid: (agent, None))

    proxy.run_tool(bound, "propose_concession", {"seats": 200})
    assert state.get(bound)["concessions_offered"] == ["a thirty-day pilot"]

    proxy.run_tool(bound, "propose_concession", {"seats": 200})
    assert state.get(bound)["concessions_offered"] == ["a thirty-day pilot",
                                                       "onboarding included"]
    assert "lead_state" in [e["type"] for e in events], "the panel has to show it happening"


def test_the_seat_count_is_taken_from_the_lead_when_the_model_omits_it(bound, agent,
                                                                       monkeypatch):
    """The call already knows how many seats. Making the model repeat it is a chance for
    it to repeat it wrongly."""
    monkeypatch.setattr(proxy, "_bound", lambda sid: (agent, None))
    state.update(bound, seat_count=10)

    result = proxy.run_tool(bound, "propose_concession", {})
    assert result["give"] == "a thirty-day pilot"
    result = proxy.run_tool(bound, "propose_concession", {})
    assert result["give"] == "annual prepay terms", "10 seats cannot justify the 50-seat rung"


def test_the_chip_shows_both_halves_of_the_trade(bound, agent, monkeypatch, events):
    """A chip reading only "pilot offered" hides the thing that makes it a trade rather
    than a giveaway, which is the one thing a judge — or an operator — needs to see."""
    monkeypatch.setattr(proxy, "_bound", lambda sid: (agent, None))
    proxy.run_tool(bound, "propose_concession", {"seats": 200})

    chip = next(e["data"]["result_summary"] for e in events
                if e["type"] == "tool_call" and e["data"]["name"] == "propose_concession")
    assert chip == "a thirty-day pilot ← an exec sponsor and a decision date"


def test_turning_negotiation_off_removes_the_tool_entirely(agent):
    """A tool the model can still see is a tool it will still try (tools/__init__ header)."""
    from backend import tools
    off = agent.model_copy(update={
        "tools_enabled": agent.tools_enabled.model_copy(update={"negotiation": False})})
    assert "propose_concession" in tools.enabled_names(agent)
    assert "propose_concession" not in tools.enabled_names(off)


def test_the_console_and_the_backend_seed_the_same_pricing_strategy():
    """The default strategy is written out twice — models.py for a seeded agent, the
    console's blank config for one built in the UI. Nothing at runtime compares them, so
    a drift means two agents negotiate differently and nobody is told. This is the only
    thing that would notice."""
    import pathlib
    from backend.models import DEFAULT_STRATEGIES

    page = (pathlib.Path(__file__).parent.parent
            / "console" / "app" / "agents" / "[id]" / "page.tsx").read_text(encoding="utf-8")
    assert DEFAULT_STRATEGIES["pricing"] in page, (
        "console/app/agents/[id]/page.tsx has drifted from DEFAULT_STRATEGIES['pricing']")


def test_the_model_cannot_claim_a_concession_it_did_not_make():
    """concessions_offered is deliberately absent from the extractor's schema: it is a
    record of tool calls, not of things said. A model able to write it could add a
    promise nobody authorised straight into the CRM."""
    from backend import tools
    fields = tools.LEAD_STATE_SPEC["parameters"]["properties"]
    assert "concessions_offered" not in fields
