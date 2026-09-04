"""Notion, both directions, with the network stubbed.

Same contract as test_integrations: nothing here may reach Notion. The interesting part
is not the HTTP, it is the mapping — the operator owns the column layout, so the tests
that matter are the ones about a database that does not look like ours.
"""
import pytest

from backend.models import AgentSecrets
from backend.tools import crm, notion

LEAD = {
    "session_id": "sess_n", "company": "Acme", "email": "ops@acme.test", "seat_count": 200,
    "use_case": "onboarding", "objections_raised": ["pricing"],
    "competitor_mentions": ["Northbeam"], "qualification": "hot",
    "bant": {"budget": 3, "authority": 2, "need": 2, "timeline": 2},
}

FULL_SCHEMA = {
    "Name": "title", "Email": "email", "Company": "rich_text", "Seats": "number",
    "Qualification": "select", "Notes": "rich_text", "Demo": "date",
}

CONNECTED = AgentSecrets(notion_token="ntn_TESTVALUE", notion_leads_db="db_leads")


@pytest.fixture
def sent(monkeypatch):
    """Notion configured and pre-resolved; every request captured instead of sent."""
    notion._pages.clear()
    notion._schemas.clear()
    notion._schemas["db_leads"] = ("ds_leads", dict(FULL_SCHEMA))
    captured: list[tuple[str, str, dict | None]] = []

    def fake(secrets, method, path, payload=None):
        captured.append((method, path, payload))
        return {"id": "page_1"} if path == "pages" else {}

    monkeypatch.setattr(notion, "_call", fake)
    return captured


# --- writing the lead out ---------------------------------------------------------------

def test_nothing_is_written_without_a_database(secrets, monkeypatch):
    """PRD 16: an unconfigured integration is a no-op, never an error on the call."""
    monkeypatch.setattr(notion, "_call", lambda *a, **k: pytest.fail("reached the network"))
    notion.upsert_lead(secrets, dict(LEAD))
    notion.log_booking(secrets, dict(LEAD), {"booking_id": "b1"})


def test_a_token_without_a_leads_database_still_writes_nothing(monkeypatch):
    """Pricing-only is a real setup: import tiers from Notion, keep the CRM in HubSpot."""
    monkeypatch.setattr(notion, "_call", lambda *a, **k: pytest.fail("reached the network"))
    notion.upsert_lead(AgentSecrets(notion_token="ntn_TESTVALUE"),
                       dict(LEAD))


def test_the_lead_lands_in_the_operators_own_columns(sent):
    notion.upsert_lead(CONNECTED, dict(LEAD))
    method, path, payload = sent[0]
    assert (method, path) == ("POST", "pages")
    assert payload["parent"] == {"type": "data_source_id", "data_source_id": "ds_leads"}

    props = payload["properties"]
    assert props["Name"]["title"][0]["text"]["content"] == "Acme"
    assert props["Email"]["email"] == "ops@acme.test"
    assert props["Seats"]["number"] == 200
    assert props["Qualification"]["select"]["name"] == "hot"
    assert "Northbeam" in props["Notes"]["rich_text"][0]["text"]["content"]


def test_a_resync_updates_the_row_instead_of_adding_another(sent):
    """The 10 s debounce means a long call syncs repeatedly; one call must be one row."""
    notion.upsert_lead(CONNECTED, dict(LEAD))
    notion.upsert_lead(CONNECTED, dict(LEAD, seat_count=250))

    assert [m for m, _, _ in sent] == ["POST", "PATCH"]
    assert sent[1][1] == "pages/page_1"
    assert sent[1][2]["properties"]["Seats"]["number"] == 250


def test_the_booking_folds_into_the_same_row_as_the_lead(sent):
    notion.upsert_lead(CONNECTED, dict(LEAD))
    notion.log_booking(CONNECTED, dict(LEAD),
                       {"booking_id": "b1", "slot_iso": "2026-09-10T10:00:00+00:00",
                        "email": "ops@acme.test"})
    assert sent[1][1] == "pages/page_1", "a booking must not start a second row"
    assert sent[1][2]["properties"]["Demo"]["date"]["start"].startswith("2026-09-10")


def test_a_database_missing_a_column_loses_that_field_not_the_row(sent):
    """The operator's schema is theirs. A partial one degrades; it does not 400 the write."""
    notion._schemas["db_leads"] = ("ds_leads", {"Lead": "title", "Email": "email"})
    notion.upsert_lead(CONNECTED, dict(LEAD))

    props = sent[0][2]["properties"]
    assert props["Lead"]["title"][0]["text"]["content"] == "Acme", "the title column is found by type"
    assert set(props) == {"Lead", "Email"}


def test_a_computed_column_is_never_written_to(sent):
    """Notion rejects a write to a formula or rollup, and rejects the whole page with it."""
    notion._schemas["db_leads"] = ("ds_leads", {"Name": "title", "Seats": "formula"})
    notion.upsert_lead(CONNECTED, dict(LEAD))
    assert set(sent[0][2]["properties"]) == {"Name"}


def test_a_database_with_nothing_we_can_fill_writes_nothing(sent, capsys):
    notion._schemas["db_leads"] = ("ds_leads", {"Owner": "people"})
    notion.upsert_lead(CONNECTED, dict(LEAD))
    assert sent == []
    assert "no column matched" in capsys.readouterr().out


@pytest.mark.parametrize("column", ["Per Seat / Month", "per_seat_month", "PERSEATMONTH"])
def test_column_names_are_matched_the_way_an_operator_writes_them(column):
    assert notion._key(column) == "perseatmonth"


def test_no_email_means_no_notion_row_either(secrets, monkeypatch):
    """A row per call with no way to contact anybody is landfill in someone's workspace."""
    monkeypatch.setattr(notion, "upsert_lead",
                        lambda *a: pytest.fail("wrote a lead with no email"))
    crm.sync_contact(CONNECTED, dict(LEAD, email=None), force=True)


def test_the_crm_write_still_reaches_notion_without_a_hubspot_token(monkeypatch):
    """The two destinations are independent: HubSpot unconfigured must not skip Notion."""
    reached = []
    monkeypatch.setattr(notion, "upsert_lead", lambda s, lead: reached.append(lead))
    crm.sync_contact(CONNECTED, dict(LEAD), force=True)
    assert reached, "Notion was skipped because HubSpot had no token"


# --- secrets stay write-only ------------------------------------------------------------

def test_the_notion_token_is_masked_but_the_database_ids_are_not():
    """An id is in the page URL already; the token is the only secret of the three."""
    masked = CONNECTED.masked()
    assert masked["notion_token"] == "set"
    assert masked["notion_leads_db"] == "db_leads"
    assert AgentSecrets().masked()["notion_token"] is None


def test_the_row_is_labelled_with_the_person_not_the_company(sent):
    """An operator reads the title column down the page to decide who to call back, and a
    list of company names does not tell them who that is. The prospect's name had nowhere
    to live until now: it was an argument to book_meeting and was discarded after."""
    notion.upsert_lead(CONNECTED, dict(LEAD, name="Keshav"))
    props = sent[0][2]["properties"]
    assert props["Name"]["title"][0]["text"]["content"] == "Keshav"


def test_a_lead_with_no_name_yet_still_gets_a_labelled_row(sent):
    """Names arrive mid-call, and a row that appears before one does must not be blank."""
    notion.upsert_lead(CONNECTED, dict(LEAD))
    assert sent[0][2]["properties"]["Name"]["title"][0]["text"]["content"] == "Acme"


def test_the_booking_writes_the_time_whatever_the_operator_called_the_column(sent):
    """Demo, Date and Date Time are the same column to an operator. Only the ones that
    exist are written, so this costs nothing on a database that has just one of them."""
    for column in ("Demo", "Date", "Date Time"):
        notion._pages.clear()
        notion._schemas["db_leads"] = ("ds_leads", {"Name": "title", column: "date"})
        sent.clear()
        notion.log_booking(CONNECTED, dict(LEAD, name="Keshav"),
                           {"booking_id": "b1", "slot_iso": "2026-09-10T10:00:00+00:00",
                            "email": "ops@acme.test", "name": "Keshav"})
        props = sent[0][2]["properties"]
        assert props[column]["date"]["start"].startswith("2026-09-10"), column


def test_purpose_is_written_from_the_use_case_already_captured(sent):
    """Purpose is what an operator calls the column; use_case is what the state calls the
    field. Aliasing beats asking the model to record the same thing twice."""
    notion._schemas["db_leads"] = ("ds_leads", {"Name": "title", "Purpose": "rich_text"})
    notion.upsert_lead(CONNECTED, dict(LEAD, use_case="onboarding"))
    props = sent[0][2]["properties"]
    assert props["Purpose"]["rich_text"][0]["text"]["content"] == "onboarding"
