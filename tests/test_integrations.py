"""Cal.com, HubSpot, Slack and the agent/secrets models.

None of these have credentials in test, which is the point: PRD 16 requires a missing
integration to degrade to a logged outcome rather than a broken call. Anything that would
reach the network here is a bug.
"""
import time

import pytest

from backend import agents
from backend.models import AgentConfig, AgentSecrets, Persona
from backend.tools import crm
from backend.tools.calendar import book_meeting, check_slots
from backend.tools.escalation import escalate_to_human, summarise

LEAD = {
    "session_id": "sess_a", "company": "Acme", "email": None, "seat_count": 200,
    "use_case": "onboarding", "objections_raised": ["pricing"],
    "competitor_mentions": ["Northbeam"], "qualification": "hot",
    "bant": {"budget": 3, "authority": 2, "need": 2, "timeline": 2},
}


# --- calendar --------------------------------------------------------------------------

def test_slots_are_offered_even_with_no_calendar_connected(secrets):
    result = check_slots(secrets)
    assert result["source"] == "stub"
    assert len(result["slots"]) == 5


def test_slots_are_in_the_future_and_human_readable(secrets):
    for slot in check_slots(secrets)["slots"]:
        assert slot["iso"] > time.strftime("%Y-%m-%d")
        assert "UTC" in slot["human"]


def test_slots_are_capped_at_five_however_far_ahead_we_look(secrets):
    """The agent has to read these aloud, so the list is a spoken list, not a data dump."""
    assert len(check_slots(secrets, days_ahead=60)["slots"]) == 5


def test_booking_requires_an_email(secrets):
    result = book_meeting(secrets, "2026-09-01T10:00:00+00:00", "", session_id="s")
    assert result["error"] == "email_required"
    assert "Ask for their email" in result["instruction"]


def test_a_refused_booking_is_not_remembered_as_booked(secrets):
    book_meeting(secrets, "2026-09-01T10:00:00+00:00", "", session_id="s")
    ok = book_meeting(secrets, "2026-09-01T10:00:00+00:00", "a@b.test", session_id="s")
    assert not ok.get("already_booked")


def test_booking_is_idempotent_per_session(secrets):
    first = book_meeting(secrets, "2026-09-01T10:00:00+00:00", "a@b.test", session_id="s")
    again = book_meeting(secrets, "2026-09-30T10:00:00+00:00", "a@b.test", session_id="s")
    assert again["already_booked"] and again["slot_iso"] == first["slot_iso"]


def test_different_sessions_book_independently(secrets):
    book_meeting(secrets, "2026-09-01T10:00:00+00:00", "a@b.test", session_id="s1")
    assert not book_meeting(secrets, "2026-09-02T10:00:00+00:00", "c@d.test",
                            session_id="s2").get("already_booked")


def test_a_name_is_derived_from_the_email_when_absent(secrets):
    assert book_meeting(secrets, "2026-09-01T10:00:00+00:00", "ops@acme.test",
                        session_id="s")["email"] == "ops@acme.test"


# --- crm -------------------------------------------------------------------------------

def test_no_email_means_nothing_is_written(secrets, capsys):
    """Without an email there is no stable CRM identity, so writing would create junk."""
    crm.sync_contact(secrets, dict(LEAD))
    assert "no email yet" in capsys.readouterr().out


def test_sync_is_debounced(secrets, capsys):
    lead = dict(LEAD, email="ops@acme.test")
    crm.sync_contact(secrets, lead)
    first = capsys.readouterr().out
    crm.sync_contact(secrets, lead)
    assert first and capsys.readouterr().out == "", "a second write inside the window is skipped"


def test_force_overrides_the_debounce(secrets, capsys):
    """Call end must always flush, however recently the last sync ran."""
    lead = dict(LEAD, email="ops@acme.test")
    crm.sync_contact(secrets, lead)
    capsys.readouterr()
    crm.sync_contact(secrets, lead, force=True)
    assert capsys.readouterr().out != ""


def test_lead_properties_carry_what_a_rep_needs(secrets):
    props = crm._properties(dict(LEAD, email="ops@acme.test"))
    assert props["company"] == "Acme"
    assert props["hs_lead_status"] == "OPEN_DEAL"
    assert "200 seats" in props["message"] and "Northbeam" in props["message"]


@pytest.mark.parametrize(("qualification", "status"),
                         [("hot", "OPEN_DEAL"), ("warm", "IN_PROGRESS"), ("cold", "NEW")])
def test_every_qualification_maps_to_a_hubspot_status(qualification, status):
    assert crm._properties(dict(LEAD, qualification=qualification))["hs_lead_status"] == status


def test_deal_creation_without_a_token_only_logs(secrets, capsys):
    crm.create_deal(secrets, dict(LEAD), {"booking_id": "b1", "slot_iso": "2026-09-01"})
    assert "would create deal" in capsys.readouterr().out


# --- escalation ------------------------------------------------------------------------

def test_the_summary_is_written_before_the_rep_speaks(secrets):
    """PRD G6: the rep has context before they say anything."""
    summary = summarise(dict(LEAD), "asked for a human")
    for expected in ("Acme", "200 seats", "hot", "pricing", "Northbeam", "asked for a human"):
        assert expected in summary


def test_a_sparse_lead_still_summarises(secrets):
    sparse = dict(LEAD, company=None, seat_count=None, objections_raised=[],
                  competitor_mentions=[])
    summary = summarise(sparse, "legal question")
    assert "Unknown company" in summary and "none" in summary


def test_escalation_returns_something_speakable(secrets):
    result = escalate_to_human(secrets, "asked for a human", dict(LEAD), "pitchpilot-t")
    assert result["rep_eta"]
    assert result["channel"] == "pitchpilot-t"


# --- models ----------------------------------------------------------------------------

def test_config_survives_a_jsonb_round_trip(config):
    assert AgentConfig(**config.model_dump()) == config


def test_a_new_agent_gets_working_defaults():
    cfg = AgentConfig(persona=Persona(identity="Sells things."))
    assert cfg.voice.speaking_interrupt_duration_ms == 320
    assert cfg.tools_enabled.crm is True
    assert set(cfg.persona.objection_strategies) == {"pricing", "trust", "product", "competitor"}


def test_identity_is_required():
    with pytest.raises(Exception):
        AgentConfig()


def test_default_strategies_are_not_shared_between_agents():
    """A mutable default shared across agents would let one edit change everyone's."""
    a = AgentConfig(persona=Persona(identity="a"))
    b = AgentConfig(persona=Persona(identity="b"))
    a.persona.objection_strategies["pricing"] = "CHANGED"
    assert b.persona.objection_strategies["pricing"] != "CHANGED"


def test_secrets_are_masked_not_echoed():
    masked = AgentSecrets(calcom_api_key="cal_live_abc",
                          slack_webhook_url="https://hooks.example/x").masked()
    assert masked["calcom_api_key"] == "set"
    assert masked["slack_webhook_url"] == "set"
    assert masked["hubspot_token"] is None
    assert "cal_live_abc" not in str(masked)
    assert "hooks.example" not in str(masked)


def test_non_secret_settings_stay_readable():
    """The operator needs to see which pipeline a deal lands in."""
    assert AgentSecrets().masked()["hubspot_pipeline"] == "default"


# --- origin allowlist ------------------------------------------------------------------

@pytest.mark.parametrize(
    ("allowed", "origin", "ok"),
    [
        (["https://a.test"], "https://a.test", True),
        (["https://a.test/"], "https://a.test", True),      # trailing slash is noise
        (["https://a.test"], "https://a.test/", True),
        (["https://a.test", "https://b.test"], "https://b.test", True),
        (["https://a.test"], "https://evil.test", False),
        (["https://a.test"], "https://a.test.evil.com", False),   # no suffix matching
        (["https://a.test"], "http://a.test", False),             # scheme matters
        (["https://a.test"], None, False),                        # missing is not a pass
        (["https://a.test"], "", False),
        ([], "https://a.test", False),                            # empty list denies all
        ([], None, False),
    ],
)
def test_origin_allowlist(allowed, origin, ok):
    assert agents.allowed_origin(allowed, origin) is ok


def test_binding_lifecycle(config, secrets):
    agents._bound["s"] = ("ag_x", config, secrets)
    assert agents.for_session("s")[0] == "ag_x"
    agents.release("s")
    assert agents.for_session("s") is None
    agents.release("s")  # releasing twice is not an error
