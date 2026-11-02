"""Bewohnerfunktionen: geschützte Meldungen, Filter und verständliche Fehler."""

import sqlite3
from html import unescape
from urllib.parse import parse_qs, urlsplit

import pytest

from app import db, middleware
from tests import test_capabilities as access
from tests.conftest import ADMIN, VALID

reader_client = access.reader_client
clock = access.clock
HTML = {"Accept": "text/html"}


def add_entries(count, slug="werkstatt", condition="Sauber", remark="Werkbank gereinigt"):
    with db.db_connect() as conn:
        room = db.load_room_by_slug(conn, slug)
        conn.executemany(
            """INSERT INTO usage_sessions(room_id, person_name, house, condition, remark, started_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (
                    room["id"],
                    f"Bewohner-{index:02}",
                    "GH12",
                    condition,
                    remark,
                    "2026-11-01T12:00:00+00:00",
                )
                for index in range(count)
            ],
        )


def test_browser_denial_keeps_navigation_and_api_formats(reader_client):
    add_entries(1, remark="PRIVATE-REMARK")
    response = reader_client.get("/logbuch", headers=HTML)
    assert response.status_code == 403
    assert "Hauptnavigation" in response.text and "Raum-QR-Code scannen" in response.text
    assert "PRIVATE-REMARK" not in response.text
    assert "www-authenticate" not in response.headers and "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "private, no-store"
    assert reader_client.get("/logbuch").json()["detail"].startswith("Leseberechtigung")
    for path in ("/rooms/latest-status", "/uploads/unknown.png", "/r/sauna/qr.pdf"):
        data = reader_client.get(path, headers=HTML)
        assert data.status_code == 403 and "detail" in data.json()


def test_latest_status_is_minimal_and_skips_deleted_and_inactive(reader_client):
    add_entries(2)
    add_entries(1, condition="Problem/Defekt")
    add_entries(1, "sauna", "Aufräumen nötig")
    with db.db_connect() as conn:
        conn.execute("UPDATE usage_sessions SET condition='Aufräumen nötig' WHERE id=2")
        conn.execute("UPDATE usage_sessions SET deleted_at='deleted' WHERE id=3")
        conn.execute("UPDATE rooms SET is_active=0 WHERE slug='sauna'")
    assert "data-room-status-url" not in reader_client.get("/").text
    access.grant(reader_client, "werkstatt")
    response = reader_client.get("/rooms/latest-status")
    assert response.status_code == 200
    rows = response.json()
    assert all(set(row) == {"slug", "condition", "started_at"} for row in rows)
    assert next(row for row in rows if row["slug"] == "werkstatt")["condition"] == "Aufräumen nötig"
    assert next(row for row in rows if row["slug"] == "ruheraum")["started_at"] is None
    assert not any(row["slug"] == "sauna" for row in rows)
    shell = reader_client.get("/").text
    assert 'data-room-status-url="/rooms/latest-status"' in shell
    assert "Bewohner-" not in shell and "2026-11-01T12:00:00" not in shell


def test_latest_status_renews_success_but_blocks_expiry_and_rotation(reader_client, clock):
    access.grant(reader_client)
    before = access.stored_session(reader_client)["expires_at"]
    clock["now"] += 60
    reader_client.get("/")
    assert access.stored_session(reader_client)["expires_at"] == before
    response = reader_client.get("/rooms/latest-status")
    access.assert_cookie_expiry(response, clock["now"], before + 60)
    access.rotation(reader_client)
    denied = reader_client.get("/rooms/latest-status")
    assert denied.status_code == 403 and "set-cookie" not in denied.headers
    access.grant(reader_client)
    clock["now"] = access.stored_session(reader_client)["expires_at"]
    assert reader_client.get("/rooms/latest-status").status_code == 403


def test_status_race_never_delivers_private_body(reader_client, monkeypatch):
    access.grant(reader_client)
    add_entries(1)
    monkeypatch.setattr(middleware, "renew_reader_session", lambda _: None)
    response = reader_client.get("/rooms/latest-status")
    assert response.status_code == 403 and "2026-11-01" not in response.text
    response = reader_client.get("/logbuch", headers=HTML)
    assert response.status_code == 403 and "Hauptnavigation" in response.text
    assert "Bewohner-" not in response.text


def test_status_admin_scope(reader_client):
    assert reader_client.get("/admin/rooms/latest-status").status_code == 401
    response = reader_client.get("/admin/rooms/latest-status", auth=ADMIN)
    assert response.status_code == 200
    assert (
        'data-room-status-url="/admin/rooms/latest-status"'
        in reader_client.get("/", auth=ADMIN).text
    )


def test_logbook_pagination_filters_and_tie_order(reader_client):
    add_entries(42, condition="Problem/Defekt", remark="Defekt am Bohrer")
    add_entries(1, "sauna")
    access.grant(reader_client)
    query = {"raum": "werkstatt", "zustand": "Problem/Defekt", "q": "Bohrer"}
    response = reader_client.get("/logbuch", params=query)
    assert response.text.index("Bewohner-41") < response.text.index("Bewohner-40")
    assert "Bewohner-22" in response.text and "Bewohner-21" not in response.text
    import re

    older = unescape(re.search(r'href="([^"]+)" rel="next"', response.text)[1])
    assert parse_qs(urlsplit(older).query) == {
        **{key: [value] for key, value in query.items()},
        "seite": ["2"],
    }
    second = reader_client.get(older)
    assert "Bewohner-21" in second.text and "Bewohner-02" in second.text
    assert "Bewohner-22" not in second.text and "Bewohner-01" not in second.text
    last = reader_client.get("/logbuch", params={**query, "seite": 3})
    assert "Bewohner-01" in last.text and 'rel="next"' not in last.text
    empty = reader_client.get("/logbuch", params={**query, "seite": 4})
    assert "Zur ersten Seite" in empty.text


@pytest.mark.parametrize("term", ["%", "_", "\\"])
def test_literal_search_and_deleted_entries(reader_client, term):
    add_entries(1, remark=f"Sonderzeichen {term}")
    add_entries(1, remark="normal")
    access.grant(reader_client)
    response = reader_client.get("/logbuch", params={"q": term})
    assert (
        "Sonderzeichen" in response.text
        and '<p class="entry-remark">normal</p>' not in response.text
    )
    with db.db_connect() as conn:
        conn.execute("UPDATE usage_sessions SET deleted_at='deleted' WHERE id=1")
    assert "Keine passenden Einträge" in reader_client.get("/logbuch", params={"q": term}).text


@pytest.mark.parametrize(
    "query",
    [
        {"seite": "-1"},
        {"seite": "abc"},
        {"seite": "9" * 100},
        {"raum": "missing"},
        {"zustand": "bad"},
        {"q": "x" * 101},
    ],
)
def test_invalid_logbook_filter_is_html(reader_client, query):
    access.grant(reader_client)
    response = reader_client.get("/logbuch", params=query, headers=HTML)
    assert response.status_code == 400 and "Hauptnavigation" in response.text
    assert "Filter zurücksetzen" in response.text and "set-cookie" not in response.headers


def test_form_errors_preserve_values_and_mark_fields(client):
    response = client.post("/r/werkstatt/submit", data={**VALID, "condition": "bad"}, headers=HTML)
    assert response.status_code == 400
    assert 'id="condition" tabindex="-1" aria-invalid="true"' in response.text
    assert 'value="Test Person"' in response.text and 'href="#condition"' in response.text
    missing = {key: value for key, value in VALID.items() if key != "condition"}
    response = client.post("/r/werkstatt/submit", data=missing, headers=HTML)
    assert response.status_code == 422 and 'value="Test Person"' in response.text
    assert 'href="#condition"' in response.text
    response = client.post("/hilfe", data={"person_name": "Retained"}, headers=HTML)
    assert response.status_code == 422 and 'value="Retained"' in response.text
    response = client.post(
        "/r/werkstatt/submit", data={**VALID, "images": "invalid-file"}, headers=HTML
    )
    assert response.status_code == 422 and 'href="#images"' in response.text


def test_browser_middleware_errors_and_database_failure(client, monkeypatch):
    monkeypatch.setattr(middleware, "MAX_REQUEST_SIZE_BYTES", 10)
    response = client.post("/hilfe", content=b"x" * 11, headers=HTML)
    assert response.status_code == 413 and "Hauptnavigation" in response.text
    monkeypatch.setattr(middleware, "MAX_REQUEST_SIZE_BYTES", 1024)
    monkeypatch.setattr(middleware, "consume_rate_limit", lambda _: 25)
    response = client.post("/hilfe", data={"note": "hello"}, headers=HTML)
    assert response.status_code == 429 and response.headers["retry-after"] == "25"
    assert "25 Sekunden" in response.text

    def unavailable():
        raise sqlite3.OperationalError("PRIVATE-DATABASE-ERROR")

    monkeypatch.setattr("app.routes.public.db_connect", unavailable)
    response = client.get("/", headers=HTML)
    assert response.status_code == 503 and "Hauptnavigation" in response.text
    assert "PRIVATE-DATABASE-ERROR" not in response.text


def test_help_and_room_links(client):
    help_page = client.get("/hilfe").text
    assert 'id="qr-zugang"' in help_page and "allen Raumlogbüchern" in help_page
    shell = client.get("/").text
    assert 'class="room-card-link" href="/r/werkstatt"' in shell
    assert 'data-href="/r/werkstatt"' not in shell
    assert "Hauptnavigation" in client.get("/r/missing", headers=HTML).text
