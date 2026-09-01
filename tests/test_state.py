"""Lead state merge semantics and BANT derivation (PRD 7)."""
import pytest

from backend import state


def test_new_state_has_every_documented_field():
    s = state.new_state("sess_a")
    assert set(s) == {
        "session_id", "company", "email", "industry", "use_case", "seat_count",
        "budget_signal", "timeline", "objections_raised", "competitor_mentions",
        "bant", "qualification", "next_action", "notes",
    }
    assert s["qualification"] == "cold"
    assert s["bant"] == {"budget": 0, "authority": 0, "need": 0, "timeline": 0}


def test_get_is_idempotent_and_returns_the_same_object():
    assert state.get("sess_a") is state.get("sess_a")


def test_scalar_updates_overwrite():
    state.update("s", seat_count=20)
    assert state.update("s", seat_count=200)["seat_count"] == 200


def test_none_never_clears_a_set_value():
    state.update("s", company="Acme")
    assert state.update("s", company=None)["company"] == "Acme"


def test_arrays_append_without_duplicates():
    state.update("s", objections_raised="pricing")
    state.update("s", objections_raised=["pricing", "trust"])
    assert state.get("s")["objections_raised"] == ["pricing", "trust"]


def test_a_bare_string_becomes_a_single_array_entry():
    assert state.update("s", competitor_mentions="Northbeam")["competitor_mentions"] == ["Northbeam"]


def test_bant_merges_per_key_rather_than_replacing():
    state.update("s", bant={"budget": 3, "need": 2})
    merged = state.update("s", bant={"authority": 1})["bant"]
    assert merged == {"budget": 3, "authority": 1, "need": 2, "timeline": 0}


def test_bant_ignores_keys_that_are_not_bant():
    assert "charisma" not in state.update("s", bant={"charisma": 3})["bant"]


def test_unknown_top_level_fields_are_ignored():
    """The model invents field names; they must not land in the object the console renders."""
    result = state.update("s", favourite_colour="blue")
    assert "favourite_colour" not in result


@pytest.mark.parametrize(
    ("bant", "expected"),
    [
        ({"budget": 0, "authority": 0, "need": 0, "timeline": 0}, "cold"),
        ({"budget": 2, "authority": 2, "need": 0, "timeline": 0}, "cold"),   # 4, just under warm
        ({"budget": 2, "authority": 2, "need": 1, "timeline": 0}, "warm"),   # 5, exactly warm
        ({"budget": 3, "authority": 3, "need": 2, "timeline": 0}, "warm"),   # 8, just under hot
        ({"budget": 3, "authority": 3, "need": 3, "timeline": 0}, "hot"),    # 9, exactly hot
        ({"budget": 3, "authority": 3, "need": 3, "timeline": 3}, "hot"),
    ],
)
def test_qualification_boundaries(bant, expected):
    assert state.qualify(bant) == expected


def test_qualification_is_recomputed_on_every_write():
    state.update("s", bant={"budget": 3, "authority": 3, "need": 3})
    assert state.get("s")["qualification"] == "hot"
    assert state.update("s", company="Acme")["qualification"] == "hot"


def test_qualification_cannot_be_set_by_the_model():
    """It is derived (PRD 7). A model that tries to declare itself hot must be ignored."""
    assert state.update("s", qualification="hot")["qualification"] == "cold"


def test_sessions_are_isolated():
    state.update("a", seat_count=10)
    state.update("b", seat_count=999)
    assert state.get("a")["seat_count"] == 10


def test_drop_returns_and_forgets():
    state.update("s", seat_count=5)
    assert state.drop("s")["seat_count"] == 5
    assert state.drop("s") is None
    assert state.get("s")["seat_count"] is None


# --- derived BANT ----------------------------------------------------------------------
# Left to itself the model fills every other field and almost never scores BANT, so a call
# that booked a demo still read as cold. Anything the conversation has proved is scored
# from the record instead.

def test_recorded_signals_score_themselves():
    s = state.update("s", seat_count=200, use_case="onboarding",
                     budget_signal="stretch", timeline="this_quarter")
    assert s["bant"] == {"budget": 2, "authority": 0, "need": 3, "timeline": 2}
    assert s["qualification"] == "warm"


def test_seat_count_alone_is_partial_need():
    assert state.update("s", seat_count=50)["bant"]["need"] == 2


def test_authority_is_left_to_the_model():
    """Nothing we record proves who can sign, so it is never derived."""
    assert state.update("s", seat_count=200, use_case="x",
                        budget_signal="under_budget", timeline="now")["bant"]["authority"] == 0
    assert state.update("s", bant={"authority": 3})["bant"]["authority"] == 3


def test_the_model_may_score_above_the_derived_floor():
    state.update("s", budget_signal="over_budget")          # floor of 1
    assert state.update("s", bant={"budget": 3})["bant"]["budget"] == 3


def test_the_model_cannot_score_below_the_derived_floor():
    state.update("s", timeline="now")                       # floor of 3
    assert state.update("s", bant={"timeline": 0})["bant"]["timeline"] == 3


def test_a_booked_demo_no_longer_reads_as_cold():
    """The live failure this fixes: every other field populated, qualification still cold."""
    s = state.update("s", seat_count=200, budget_signal="over_budget",
                     timeline="this_quarter", use_case="rollout", next_action="book_demo")
    assert s["qualification"] != "cold", s["bant"]


def test_nothing_learned_scores_nothing():
    assert state.update("s", company="Acme")["bant"] == {
        "budget": 0, "authority": 0, "need": 0, "timeline": 0}
    assert state.get("s")["qualification"] == "cold"


@pytest.mark.parametrize(("signal", "score"),
                         [("under_budget", 3), ("stretch", 2), ("over_budget", 1)])
def test_every_budget_signal_scores(signal, score):
    assert state.update("s", budget_signal=signal)["bant"]["budget"] == score


@pytest.mark.parametrize(("timeline", "score"),
                         [("now", 3), ("this_quarter", 2), ("exploring", 1)])
def test_every_timeline_scores(timeline, score):
    assert state.update("s", timeline=timeline)["bant"]["timeline"] == score


def test_a_pricing_objection_proves_a_budget_exists():
    """They pushed back on price, so there is a budget even if it was never named."""
    assert state.update("s", objections_raised=["pricing"])["bant"]["budget"] == 1


def test_a_named_budget_signal_outscores_the_objection_alone():
    s = state.update("s", objections_raised=["pricing"], budget_signal="under_budget")
    assert s["bant"]["budget"] == 3


def test_comparing_vendors_counts_as_an_active_evaluation():
    assert state.update("s", competitor_mentions=["Northbeam"])["bant"]["need"] == 2
    assert state.update("s", seat_count=200)["bant"]["need"] == 3


def test_agreeing_a_demo_date_is_timeline_evidence():
    assert state.update("s", next_action="book_demo")["bant"]["timeline"] == 2


def test_a_stated_timeline_still_outscores_a_booking():
    s = state.update("s", next_action="book_demo", timeline="now")
    assert s["bant"]["timeline"] == 3


def test_a_realistic_booked_call_qualifies():
    """The exact shape of a live run that previously read as cold: seats known, price
    objected to, competitor named, demo booked, and the model scoring nothing itself."""
    s = state.update("s", seat_count=200, objections_raised=["pricing"],
                     competitor_mentions=["Northbeam"], next_action="book_demo")
    assert s["bant"] == {"budget": 1, "authority": 0, "need": 3, "timeline": 2}
    assert s["qualification"] == "warm", s["bant"]


def test_numbers_arriving_as_strings_do_not_kill_the_turn():
    """ministral-8b returned BANT scores as strings on a live call; max("2", 0) raised and
    the agent spent every tool hop retrying, then escalated for no reason."""
    lead = state.update("s", seat_count="200", bant={"budget": "2", "authority": 3})
    assert lead["seat_count"] == 200
    assert lead["bant"]["budget"] == 2 and lead["bant"]["authority"] == 3


def test_nonsense_numbers_are_dropped_rather_than_stored():
    lead = state.update("s", seat_count="a couple hundred", bant={"need": "lots"})
    assert lead["seat_count"] is None
    assert lead["bant"]["need"] == 0


def test_out_of_range_scores_are_clamped():
    """The schema says 0-3. A model reading it as a percentage would pin the lead hot."""
    lead = state.update("s", bant={"budget": 90, "authority": -5})
    assert lead["bant"]["budget"] == 3 and lead["bant"]["authority"] == 0


def test_a_bant_value_that_is_not_a_dict_is_ignored():
    assert state.update("s", bant="high")["bant"] == {"budget": 0, "authority": 0,
                                                      "need": 0, "timeline": 0}
