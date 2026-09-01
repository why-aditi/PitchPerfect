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
from backend.tools import calendar as cal
from backend.tools import calendar as cal
from backend.tools.calendar import (
    _api_error, book_meeting, check_slots, clean_email)
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


def test_slots_are_in_the_future_and_speakable(secrets):
    """The human string is read aloud, so it must not contain anything a caller would not say."""
    for slot in check_slots(secrets)["slots"]:
        assert slot["iso"] > time.strftime("%Y-%m-%d")
        assert " at " in slot["human"] and slot["human"].endswith(("am", "pm"))
        assert "UTC" not in slot["human"], "a zone abbreviation gets read out verbatim"
        assert not any(c.isdigit() for c in slot["human"].split(" at ")[0]), "no date number"


def test_slots_are_capped_at_five_however_far_ahead_we_look(secrets):
    """The agent has to read these aloud, so the list is a spoken list, not a data dump."""
    assert len(check_slots(secrets, days_ahead=60)["slots"]) == 5


def test_booking_requires_an_email(secrets):
    result = book_meeting(secrets, "2026-09-01T10:00:00+00:00", "", session_id="s")
    assert result["error"] == "email_required"
    assert "Ask for their email" in result["instruction"]


def test_a_refused_booking_is_not_remembered_as_booked(secrets):
    book_meeting(secrets, "2026-09-01T10:00:00+00:00", "", session_id="s")
    ok = book_meeting(secrets, "2026-09-01T10:00:00+00:00", "a@b.test", name="Dana Reyes", session_id="s")
    assert not ok.get("already_booked")


def test_booking_the_same_slot_twice_is_one_meeting(secrets):
    first = book_meeting(secrets, "2026-09-01T10:00:00+00:00", "a@b.test", name="Dana Reyes", session_id="s")
    again = book_meeting(secrets, "2026-09-01T10:00:00+00:00", "a@b.test", name="Dana Reyes", session_id="s")
    assert again["already_booked"] and again["slot_iso"] == first["slot_iso"]


def test_a_second_slot_moments_later_is_the_model_repeating_itself(secrets):
    """A live call booked and rescheduled 17 seconds apart off one agreement, and the
    prospect got a confirmation email and a "your meeting moved" email for one demo."""
    first = book_meeting(secrets, "2026-09-01T10:00:00+00:00", "a@b.test", name="Dana Reyes", session_id="s")
    again = book_meeting(secrets, "2026-09-30T10:00:00+00:00", "a@b.test", name="Dana Reyes", session_id="s")
    assert again["already_booked"] and again["slot_iso"] == first["slot_iso"]
    assert again["ignored_slot"] == "2026-09-30T10:00:00+00:00"


def test_a_different_slot_moves_the_meeting_instead_of_refusing(secrets):
    """"Actually, can we do the 30th?" is the commonest thing a prospect says after agreeing."""
    first = book_meeting(secrets, "2026-09-01T10:00:00+00:00", "a@b.test", name="Dana Reyes", session_id="s")
    cal._booked["s"]["booked_at"] -= cal.SETTLE_S + 1     # a real change of mind takes time
    moved = book_meeting(secrets, "2026-09-30T10:00:00+00:00", "a@b.test", name="Dana Reyes", session_id="s")
    assert moved["slot_iso"] == "2026-09-30T10:00:00+00:00"
    assert moved["rescheduled_from"] == first["slot_iso"]
    assert moved["booking_id"] == first["booking_id"], "one booking, moved"


def test_an_email_dictated_over_the_phone_still_books(secrets):
    result = book_meeting(secrets, "2026-09-01T10:00:00+00:00",
                          "Aditi dot Kala at gmail dot com", name="Aditi Kala", session_id="s")
    assert result["email"] == "aditi.kala@gmail.com"


def test_a_mishcard_email_is_read_back_rather_than_booked(secrets):
    result = book_meeting(secrets, "2026-09-01T10:00:00+00:00", "um the usual one", name="Aditi Kala", session_id="s")
    assert result["error"] == "email_unclear"
    assert "spell it" in result["instruction"]


def test_slots_are_offered_in_the_prospects_timezone(secrets):
    """The model relays what they said, not an IANA name, and an unknown one must not raise."""
    eastern = check_slots(secrets, timezone_name="Eastern")
    nonsense = check_slots(secrets, timezone_name="Narnia/Cair")
    assert eastern["timezone"] == "America/New_York"
    assert nonsense["timezone"] == "UTC", "an unknown zone costs a wrong time, never the call"
    # The stub offers 10am and 3pm local in whichever zone it was given, so the spoken
    # strings match across zones and it is the underlying instants that move.
    assert eastern["slots"][0]["iso"] != nonsense["slots"][0]["iso"]


def test_different_sessions_book_independently(secrets):
    book_meeting(secrets, "2026-09-01T10:00:00+00:00", "a@b.test", name="Dana Reyes", session_id="s1")
    assert not book_meeting(secrets, "2026-09-02T10:00:00+00:00", "c@d.test", name="Dana Reyes",
                            session_id="s2").get("already_booked")


def test_a_booking_without_a_real_name_is_refused(secrets):
    """Cal.com will take the local part of the address as the attendee name, which puts
    "ops" on the invite and in the CRM. Asking is one short question."""
    for bad in (None, "", " ", "ops", "ops@acme.test"):
        result = book_meeting(secrets, "2026-09-01T10:00:00+00:00", "ops@acme.test",
                              name=bad, session_id=f"s{bad}")
        assert result["error"] == "name_required", bad
    ok = book_meeting(secrets, "2026-09-01T10:00:00+00:00", "ops@acme.test",
                      name="Dana Reyes", session_id="ok")
    assert ok["name"] == "Dana Reyes"


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


# --- what the agent is told when Cal.com says no -----------------------------------------

class _Resp:
    def __init__(self, status): self.response = type("r", (), {"status_code": status})()


def test_a_taken_slot_tells_the_agent_to_offer_another():
    """A live call hit a 409 and stopped dead: the model got a URL and a status line and had
    no idea the slot had simply gone."""
    result = _api_error(_Resp(409))
    assert result["error"] == "slot_taken"
    assert "check_slots" in result["instruction"]


def test_a_rejected_key_tells_the_agent_to_fall_back_to_email():
    result = _api_error(_Resp(401))
    assert result["error"] == "calendar_unavailable"
    assert "send_followup" in result["instruction"]


def test_every_booking_failure_carries_an_instruction():
    for status in (409, 401, 403, 400, 429, 500):
        assert _api_error(_Resp(status))["instruction"], status


def test_half_an_address_is_not_an_address():
    """A live call stored "gmail.com" as the prospect's email and carried it to the CRM."""
    assert clean_email("gmail.com") is None
    assert clean_email("um, hang on") is None
    assert clean_email("") is None
    assert clean_email("Dana dot Reyes at gmail dot com") == "dana.reyes@gmail.com"
