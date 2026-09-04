"""Leads mirrored out to Notion during a call. One direction only.

The same lead HubSpot gets, written into a Notion database, for a team whose pipeline
lives in Notion rather than a CRM. Fire-and-forget under exactly the rule crm.py sets:
every error here is logged and swallowed, because a Notion outage must never break a
live call.

Pricing used to be read back the other way, from a Notion database into the agent's
config. It was removed: the knowledge base was always the source of truth — get_pricing
reads config.knowledge.tiers and never touched Notion — and the import could not carry
volume_break, so it offered strictly less than what an operator had already configured.

Notion's schema is the operator's, not ours. Rather than demand a column layout, the
data source schema is fetched once and writes are filtered down to the columns that
actually exist — a database missing "Seats" loses the seat count, not the whole row.
"""
import re

import httpx

from ..models import AgentSecrets

API = "https://api.notion.com/v1"
# Notion is date-versioned and the header is mandatory. Every shape below is written
# against this version — bump it and re-check the data-source calls, which is the part
# that moved last time.
VERSION = "2026-03-11"
TIMEOUT = 8

# Page id per session, so a debounced re-sync updates the row it already created instead
# of appending a second one.
# ponytail: in memory, so a restart mid-call orphans that row and the next sync starts a
# fresh one. A session-id column plus a query-before-write would close it; not worth a
# second round trip on every sync until a restart mid-call actually happens.
_pages: dict[str, str] = {}
# database id -> (data source id, {property name: type}). Two calls, once per process.
_schemas: dict[str, tuple[str, dict[str, str]]] = {}


def _call(secrets: AgentSecrets, method: str, path: str, payload: dict | None = None) -> dict | None:
    try:
        r = httpx.request(method, f"{API}/{path}", timeout=TIMEOUT, json=payload,
                          headers={"Authorization": f"Bearer {secrets.notion_token}",
                                   "Notion-Version": VERSION})
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        print(f"[notion] {method} {path} failed: {exc!r}")
        return None


def _schema(secrets: AgentSecrets, database_id: str) -> tuple[str, dict[str, str]] | None:
    """Resolve a database id to its data source and column types.

    Operators copy a database id out of a Notion URL, but pages are created against a
    data source, so the id they have is never the id the write needs. Resolving it here
    is the difference between pasting a URL and hunting for an internal id.
    """
    if database_id in _schemas:
        return _schemas[database_id]

    db = _call(secrets, "GET", f"databases/{database_id}")
    sources = (db or {}).get("data_sources") or []
    if not sources:
        print(f"[notion] {database_id}: no data source — check the integration has access to it")
        return None

    source_id = sources[0]["id"]
    detail = _call(secrets, "GET", f"data_sources/{source_id}")
    if detail is None:
        return None
    types = {name: spec.get("type", "") for name, spec in (detail.get("properties") or {}).items()}
    _schemas[database_id] = (source_id, types)
    return _schemas[database_id]


def _value(kind: str, value) -> dict | None:
    """One Python value in whatever shape the operator's column type wants.

    The same field lands in a different envelope per type, and a mismatch 400s the whole
    page, so the column's declared type decides — never the value's Python type.
    """
    text = [{"type": "text", "text": {"content": str(value)[:2000]}}]
    if kind == "title":
        return {"title": text}
    if kind == "rich_text":
        return {"rich_text": text}
    if kind == "email":
        return {"email": str(value)}
    if kind == "phone_number":
        return {"phone_number": str(value)}
    if kind == "url":
        return {"url": str(value)}
    if kind == "number":
        try:
            return {"number": float(value)}
        except (TypeError, ValueError):
            return None
    if kind == "select":
        return {"select": {"name": str(value)[:100]}}
    if kind == "multi_select":
        items = value if isinstance(value, list) else [value]
        return {"multi_select": [{"name": str(v)[:100]} for v in items]}
    if kind == "checkbox":
        return {"checkbox": bool(value)}
    if kind == "date":
        return {"date": {"start": str(value)}}
    # A formula, rollup or relation column is computed or linked; it cannot be written to.
    return None


def _key(name: str) -> str:
    """"Per Seat / Month" and "per_seat_month" are the same column to an operator."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _properties(fields: dict, types: dict[str, str]) -> dict:
    """Match our fields to the operator's columns by normalised name, plus the title.

    Whichever column Notion marks as the title is the row's label whatever it is called,
    so a database whose first column is "Lead" works without being renamed to "Name".
    """
    by_key = {_key(name): name for name in types}
    out: dict[str, dict] = {}

    title = next((name for name, kind in types.items() if kind == "title"), None)
    if title and fields.get("name") is not None:
        out[title] = _value("title", fields["name"])

    for field, value in fields.items():
        if field == "name" or value is None or value == [] or value == "":
            continue
        column = by_key.get(_key(field))
        if column is None or column == title:
            continue
        shaped = _value(types[column], value)
        if shaped is not None:
            out[column] = shaped
    return out


def _write(secrets: AgentSecrets, database_id: str, fields: dict, page_key: str | None) -> None:
    resolved = _schema(secrets, database_id)
    if resolved is None:
        return
    source_id, types = resolved

    props = _properties(fields, types)
    if not props:
        print(f"[notion] {database_id}: no column matched {sorted(fields)} — nothing to write")
        return

    page_id = _pages.get(page_key) if page_key else None
    if page_id:
        _call(secrets, "PATCH", f"pages/{page_id}", {"properties": props})
        return

    created = _call(secrets, "POST", "pages",
                    {"parent": {"type": "data_source_id", "data_source_id": source_id},
                     "properties": props})
    if created and page_key:
        _pages[page_key] = created["id"]


def upsert_lead(secrets: AgentSecrets, lead: dict) -> None:
    """Mirror the lead row. Called from crm.sync_contact, so it inherits its debounce."""
    if not (secrets.notion_token and secrets.notion_leads_db):
        return
    objections = ", ".join(lead["objections_raised"]) or "none"
    competitors = ", ".join(lead["competitor_mentions"]) or "none"
    _write(secrets, secrets.notion_leads_db, {
        # The person first: the title column is what an operator reads down the page, and
        # a list of company names does not tell them who to call back. Company, then the
        # email, then the session are the fallbacks, so the row is never left unlabelled.
        "name": (lead.get("name") or lead.get("company") or lead.get("email")
                 or lead["session_id"]),
        "email": lead.get("email"),
        "company": lead.get("company"),
        # Same value as use case, under the name an operator is more likely to have given
        # the column. Whichever of the two exists is written; neither is invented.
        "purpose": lead.get("use_case"),
        "seats": lead.get("seat_count"),
        "qualification": lead["qualification"],
        "use case": lead.get("use_case"),
        "objections": objections,
        "competitors": competitors,
        "notes": (f"{lead.get('seat_count') or '?'} seats · "
                  f"{lead.get('use_case') or 'unknown use case'} · "
                  f"objections: {objections} · competitors: {competitors}"),
    }, page_key=lead["session_id"])


def log_booking(secrets: AgentSecrets, lead: dict, booking: dict) -> None:
    """Fold the booking into the lead's own row rather than starting a second one."""
    if not (secrets.notion_token and secrets.notion_leads_db):
        return
    _write(secrets, secrets.notion_leads_db, {
        "name": (booking.get("name") or lead.get("name") or lead.get("company")
                 or booking.get("email")),
        "email": booking.get("email") or lead.get("email"),
        # One value, three column names an operator might have used. Only the columns that
        # exist are written, so this costs nothing on a database that has one of them and
        # spares a rename on a database that has another.
        "demo": booking.get("slot_iso"),
        "date": booking.get("slot_iso"),
        "date time": booking.get("slot_iso"),
        "purpose": lead.get("use_case"),
        "booking id": booking.get("booking_id"),
        "qualification": lead["qualification"],
    }, page_key=lead["session_id"])
