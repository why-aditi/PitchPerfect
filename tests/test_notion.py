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

CONNECTED = AgentSecrets(notion_token="ntn_TESTVALUE", notion_leads_db="db_leads",
                         notion_pricing_db="db_pricing")


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
    notion.upsert_lead(AgentSecrets(notion_token="ntn_TESTVALUE", notion_pricing_db="db_p"),
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


# --- reading the pricing in -------------------------------------------------------------

def _row(**props):
    return {"properties": props}


def _title(value):
    return {"type": "title", "title": [{"plain_text": value}]}


def _number(value):
    return {"type": "number", "number": value}


@pytest.fixture
def pricing(monkeypatch):
    """Resolve db_pricing locally; the caller supplies the rows the query returns."""
    notion._schemas.clear()
    notion._schemas["db_pricing"] = ("ds_pricing", {})
    rows: list[dict] = []

    def fake(secrets, method, path, payload=None):
        return {"results": rows} if path.endswith("/query") else {}

    monkeypatch.setattr(notion, "_call", fake)
    return rows


def test_tiers_import_and_sort_by_the_band_they_start_at(pricing):
    pricing.extend([
        _row(Name=_title("Enterprise"), **{"Per seat month": _number(32),
                                           "Min seats": _number(101)}),
        _row(Name=_title("Team"), **{"Per seat month": _number(39), "Min seats": _number(1),
                                     "Max seats": _number(100),
                                     "Features": {"type": "multi_select",
                                                  "multi_select": [{"name": "SSO"}]}}),
    ])
    tiers, note = notion.fetch_tiers(CONNECTED)

    assert [t.name for t in tiers] == ["Team", "Enterprise"], "bands must read in order"
    assert (tiers[0].per_seat_month, tiers[0].max_seats) == (39.0, 100)
    assert tiers[0].features == ["SSO"]
    assert tiers[1].max_seats is None, "an open top band stays open"
    assert note is None


def test_a_pricing_table_headed_something_other_than_name_still_imports(pricing):
    pricing.append(_row(Plan=_title("Growth"), **{"Per seat month": _number(25)}))
    tiers, _ = notion.fetch_tiers(CONNECTED)
    assert [t.name for t in tiers] == ["Growth"]


def test_a_row_with_no_price_is_skipped_rather_than_imported_as_zero(pricing):
    """A tier with no number would have the agent quote a blank on a live call."""
    pricing.extend([
        _row(Name=_title("Team"), **{"Per seat month": _number(39)}),
        _row(Name=_title("Custom"), **{"Per seat month": {"type": "number", "number": None}}),
    ])
    tiers, note = notion.fetch_tiers(CONNECTED)
    assert [t.name for t in tiers] == ["Team"]
    assert "1 row(s) skipped" in note


def test_an_unusable_database_reports_why_instead_of_importing_nothing(pricing):
    pricing.append(_row(Notes={"type": "rich_text", "rich_text": [{"plain_text": "tbd"}]}))
    tiers, note = notion.fetch_tiers(CONNECTED)
    assert tiers == []
    assert "Per seat month" in note


def test_importing_without_a_pricing_database_says_so(secrets):
    tiers, note = notion.fetch_tiers(secrets)
    assert tiers == [] and "No Notion token" in note
    tiers, note = notion.fetch_tiers(AgentSecrets(notion_token="ntn_TESTVALUE"))
    assert tiers == [] and "pricing database" in note


# --- secrets stay write-only ------------------------------------------------------------

def test_the_notion_token_is_masked_but_the_database_ids_are_not():
    """An id is in the page URL already; the token is the only secret of the three."""
    masked = CONNECTED.masked()
    assert masked["notion_token"] == "set"
    assert masked["notion_leads_db"] == "db_leads"
    assert AgentSecrets().masked()["notion_token"] is None
