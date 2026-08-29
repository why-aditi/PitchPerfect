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
