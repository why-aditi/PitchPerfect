"""Pricing and battlecard tools. Every price the agent speaks comes from here (PRD 8)."""
import pytest

from backend.models import AgentConfig, Persona
from backend.tools.battlecards import get_battlecard
from backend.tools.pricing import get_pricing


@pytest.mark.parametrize(
    ("seats", "tier"),
    [(1, "Starter"), (9, "Starter"), (10, "Growth"), (20, "Growth"), (99, "Growth"),
     (100, "Enterprise"), (200, "Enterprise"), (10_000, "Enterprise")],
)
def test_tier_boundaries(config, seats, tier):
    assert get_pricing(config, seats=seats)["tier"] == tier


def test_twenty_seats_quotes_the_mid_tier(config):
    """PRD 15.1 step 1 depends on this exact behaviour."""
    assert get_pricing(config, seats=20)["tier"] == "Growth"


def test_volume_break_applies_at_its_own_threshold(config):
    assert get_pricing(config, seats=49)["per_seat_month"] == 39
    assert get_pricing(config, seats=50)["per_seat_month"] == 34
    assert get_pricing(config, seats=249)["per_seat_month"] == 32
    assert get_pricing(config, seats=250)["per_seat_month"] == 27


def test_monthly_total_uses_the_broken_price(config):
    quote = get_pricing(config, seats=250)
    assert quote["monthly_total"] == 250 * 27


def test_no_seats_means_no_total(config):
    """Without a seat count there is nothing to total, and inventing one would be a lie."""
    quote = get_pricing(config, tier="Growth")
    assert "monthly_total" not in quote and "seats" not in quote


def test_tier_lookup_is_case_insensitive(config):
    assert get_pricing(config, tier="growth")["tier"] == "Growth"
    assert get_pricing(config, tier="GROWTH")["tier"] == "Growth"


def test_unknown_tier_returns_no_data_and_lists_the_real_ones(config):
    result = get_pricing(config, tier="Platinum")
    assert result["error"] == "no_data"
    assert result["known_tiers"] == ["Starter", "Growth", "Enterprise"]


def test_named_tier_wins_over_seat_count(config):
    """The prospect asked about a specific tier; answer that, do not silently re-tier them."""
    assert get_pricing(config, tier="Starter", seats=500)["tier"] == "Starter"


def test_an_agent_with_no_pricing_says_so(config):
    empty = AgentConfig(persona=Persona(identity="x"))
    result = get_pricing(empty, seats=20)
    assert result["error"] == "no_data"
    assert "follow up" in result["instruction"]


@pytest.mark.parametrize("seats", [0, -5])
def test_nonsense_seat_counts_do_not_quote_the_top_tier(config, seats):
    """A transcription slip must never upgrade someone to Enterprise by accident."""
    result = get_pricing(config, seats=seats)
    assert result.get("tier") != "Enterprise", result


def test_battlecard_lookup_normalises_the_name(config):
    for name in ("Northbeam", "northbeam", "  NORTHBEAM  "):
        assert get_battlecard(config, name)["positioning"] == "They report, we act."


def test_battlecard_keeps_the_name_the_prospect_used(config):
    assert get_battlecard(config, "Northbeam")["competitor"] == "Northbeam"


def test_battlecard_includes_a_concession(config):
    """PRD 9: acknowledge one genuine strength before positioning."""
    assert get_battlecard(config, "Northbeam")["we_concede"] == ["Attribution depth"]


def test_unknown_competitor_returns_explicit_no_data(config):
    result = get_battlecard(config, "NobodyCorp")
    assert result["error"] == "no_data"
    assert result["competitor"] == "NobodyCorp"
    # The model must surface this rather than paper over it (PRD 8).
    assert "don't have data" in result["instruction"]
