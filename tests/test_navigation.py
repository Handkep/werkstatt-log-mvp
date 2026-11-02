"""Neue Hauptseiten und geschützte Raumvorschau mit isolierter Datenbank."""

from html.parser import HTMLParser

import pytest

from app import db
from tests import test_capabilities
from tests.conftest import VALID, admin_auth

reader_client = test_capabilities.reader_client
clock = test_capabilities.clock


@pytest.mark.parametrize("days", [1, 30, 365])
def test_privacy_displays_configured_reader_lifetime(client, monkeypatch, days):
    monkeypatch.setattr("app.routes.public.READER_SESSION_SECONDS", days * 86400)
    response = client.get("/datenschutz")
    assert response.status_code == 200
    assert f"{days} Tag{'e' if days != 1 else ''}</strong>" in response.text
    if days != 365:
        assert "365 Tage" not in response.text


class MainNavigation(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.active = False
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "nav":
            self.active = attrs.get("aria-label") == "Hauptnavigation"
        elif self.active and tag == "a":
            self.links.append([attrs["href"], "", attrs.get("aria-current")])

    def handle_endtag(self, tag):
        if tag == "nav":
            self.active = False

    def handle_data(self, data):
        if self.active and self.links:
            self.links[-1][1] += data.strip()


@pytest.mark.parametrize(
    "path,first,current",
    [
        ("/", "Räume", 0),
        ("/r/sauna", "Alle Räume", 0),
        ("/r/sauna?mode=room", "Alle Räume", 0),
        ("/logbuch", "Räume", 1),
        ("/hilfe", "Räume", 2),
    ],
)
def test_three_equal_main_pages(reader_client, path, first, current):
    test_capabilities.grant(reader_client)
    response = reader_client.get(path)
    assert response.status_code == 200
    links = MainNavigation(response.text).links
    assert [link[:2] for link in links] == [
        ["/", first],
        ["/logbuch", "Logbuch"],
        ["/hilfe", "Hilfe & Infos"],
    ]
    assert [index for index, link in enumerate(links) if link[2] == "page"] == [current]
    assert 'class="icon-button admin-entry" href="/admin"' in response.text
    assert "data-admin-menu" not in response.text
    assert 'href="/admin/nachrichten"' not in response.text


@pytest.mark.parametrize("path", ["/letzte-buchungen", "/anmerkungen", "/admin/anmerkungen"])
def test_old_urls_removed_without_redirect(client, path):
    for method in (client.get, client.post):
        response = method(path, auth=admin_auth(client), follow_redirects=False)
        assert response.status_code == 404
        assert "location" not in response.headers


def test_help_submission_and_private_messages(client):
    response = client.post("/hilfe", data={"note": "PRIVATE-HELP-MESSAGE"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/hilfe?gespeichert=1"
    assert "PRIVATE-HELP-MESSAGE" not in client.get("/hilfe?gespeichert=1").text
    assert client.get("/admin/nachrichten").status_code == 401
    assert "PRIVATE-HELP-MESSAGE" in client.get("/admin/nachrichten", auth=admin_auth(client)).text
    assert (
        client.post(
            "/hilfe", data={"note": "forged"}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )


@pytest.mark.parametrize("count", [0, 1, 2, 5])
def test_room_preview_limit_and_public_shell(reader_client, count):
    for index in range(count):
        reader_client.post("/r/werkstatt/submit", data={**VALID, "person_name": f"PREVIEW-{index}"})
    shell = reader_client.get("/r/werkstatt")
    assert "PREVIEW-" not in shell.text
    assert "data-room-bookings=" not in shell.text
    denied = reader_client.get("/r/werkstatt/recent-bookings")
    assert denied.status_code == 403
    assert "www-authenticate" not in denied.headers
    test_capabilities.grant(reader_client)
    shell = reader_client.get("/r/werkstatt")
    assert "PREVIEW-" not in shell.text
    assert 'data-room-bookings="/r/werkstatt/recent-bookings"' in shell.text
    assert 'href="/logbuch?raum=werkstatt"' in shell.text
    fragment = reader_client.get("/r/werkstatt/recent-bookings")
    assert fragment.status_code == 200
    assert fragment.text.count('class="mobile-entry-card"') == min(count, 3)
    assert "private, no-store" == fragment.headers["cache-control"]
    if not count:
        assert "Noch keine Buchungen in diesem Raum." in fragment.text


def test_preview_scopes_room_excludes_deleted_and_sorts_ties(reader_client):
    for index in range(1, 6):
        reader_client.post(
            "/r/werkstatt/submit", data={**VALID, "person_name": f"WORKSHOP-{index}"}
        )
    reader_client.post("/r/sauna/submit", data={**VALID, "person_name": "OTHER-ROOM"})
    with db.db_connect() as conn:
        conn.execute("UPDATE usage_sessions SET started_at='2026-01-01T00:00:00+00:00'")
        conn.execute(
            "UPDATE usage_sessions SET deleted_at='deleted' WHERE person_name='WORKSHOP-5'"
        )
        conn.execute("UPDATE usage_sessions SET remark='<script>bad()</script>' WHERE id=4")
    test_capabilities.grant(reader_client, "sauna")
    response = reader_client.get("/r/werkstatt/recent-bookings")
    assert response.status_code == 200
    assert response.text.index("WORKSHOP-4") < response.text.index("WORKSHOP-3")
    assert response.text.index("WORKSHOP-3") < response.text.index("WORKSHOP-2")
    assert all(name not in response.text for name in ("WORKSHOP-1", "WORKSHOP-5", "OTHER-ROOM"))
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_preview_renews_only_authorized_success(reader_client, clock):
    test_capabilities.grant(reader_client)
    original = test_capabilities.stored_session(reader_client)["expires_at"]
    clock["now"] += 60
    reader_client.get("/r/sauna")
    assert test_capabilities.stored_session(reader_client)["expires_at"] == original
    assert reader_client.get("/r/missing/recent-bookings").status_code == 404
    assert test_capabilities.stored_session(reader_client)["expires_at"] == original
    response = reader_client.get("/r/sauna/recent-bookings")
    assert response.status_code == 200
    expiry = original + 60
    assert test_capabilities.stored_session(reader_client)["expires_at"] == expiry
    test_capabilities.assert_cookie_expiry(response, clock["now"], expiry)
    test_capabilities.rotation(reader_client)
    denied = reader_client.get("/r/sauna/recent-bookings")
    assert denied.status_code == 403 and "set-cookie" not in denied.headers


def test_admin_preview_and_logbook_require_admin_session(reader_client):
    room = test_capabilities.room()
    preview = f"/admin/rooms/{room['id']}/recent-bookings"
    test_capabilities.grant(reader_client)
    assert reader_client.get(preview).status_code == 401
    response = reader_client.get(preview, auth=admin_auth(reader_client))
    assert response.status_code == 200
    shell = reader_client.get("/r/sauna", auth=admin_auth(reader_client))
    assert f'data-room-bookings="{preview}"' in shell.text
    assert 'data-viewer-upload-base="/admin/uploads/"' in shell.text
    assert (
        reader_client.get(
            "/admin/rooms/999/recent-bookings", auth=admin_auth(reader_client)
        ).status_code
        == 404
    )
    logbook = reader_client.get("/admin/logbuch", auth=admin_auth(reader_client))
    assert 'href="/admin/logbuch?raum=sauna"' in logbook.text
