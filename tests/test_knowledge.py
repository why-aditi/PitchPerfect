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


def test_a_named_tier_is_honoured_when_it_covers_the_seats(config):
    assert get_pricing(config, tier="Growth", seats=50)["tier"] == "Growth"
    assert "note" not in get_pricing(config, tier="Growth", seats=50)


def test_a_named_tier_that_cannot_serve_the_seats_is_corrected(config):
    """A live run had the model ask for Growth at 200 seats and quote $34/seat — a real
    price the prospect could never buy, since Growth stops at 99. The seat count wins and
    the swap is reported, so the agent can say why rather than silently re-tiering."""
    result = get_pricing(config, tier="Growth", seats=200)
    assert result["tier"] == "Enterprise"
    assert result["per_seat_month"] == 32
    assert "does not cover 200 seats" in result["note"]


def test_a_named_tier_alone_is_never_corrected(config):
    """With no seat count there is nothing to contradict, so answer what was asked."""
    assert get_pricing(config, tier="Starter")["tier"] == "Starter"


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


def test_the_quote_arrives_ready_to_read(config):
    """A live call turned a $780 total into "seventy-eight a month". The model is fine at the
    arithmetic and unreliable at rendering it, so it is asked to do neither."""
    assert get_pricing(config, seats=20)["spoken"] == "$39 a seat, $780 a month for 20 seats"
    assert get_pricing(config, seats=200)["spoken"] == "$32 a seat, $6,400 a month for 200 seats"
    assert get_pricing(config)["spoken"] == "$19 a seat"


def test_the_spoken_quote_uses_the_volume_break(config):
    """Growth breaks to $34 at 50 seats; the spoken line must not still say $39."""
    spoken = get_pricing(config, seats=60)["spoken"]
    assert spoken == "$34 a seat, $2,040 a month for 60 seats", spoken


def test_the_spoken_quote_matches_the_numbers_beside_it(config):
    """The two must never drift — the console shows one and the prospect hears the other."""
    for seats in (1, 9, 10, 49, 50, 99, 100, 249, 250, 1000):
        quote = get_pricing(config, seats=seats)
        assert f"{quote['monthly_total']:,.0f}" in quote["spoken"].replace(".0", ""), seats
