"""Admin-Anmeldung, Widerruf und Navigation mit ausschließlich isolierten Daten."""

import hashlib
import re
import time
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app import auth, db
from app.main import app
from tests.conftest import ADMIN, VALID, AdminSessionAuth
from tests.test_capabilities import grant


def token(response):
    return re.search(r'name="csrf_token" value="([^"]+)"', response.text)[1]


def login(client, *, username=ADMIN[0], password=ADMIN[1], target="/admin"):
    csrf = token(client.get("/admin/anmelden"))
    return client.post(
        "/admin/anmelden",
        data={"username": username, "password": password, "csrf_token": csrf, "next": target},
        follow_redirects=False,
    )


@pytest.mark.parametrize(
    "path",
    [
        "/admin",
        "/admin/nachrichten",
        "/admin/raumzugaenge",
        "/admin/session/1",
        "/admin/logbuch?raum=sauna&q=abc",
    ],
)
def test_browser_redirect_and_api_denial(client, path):
    response = client.get(path, headers={"Accept": "text/html"}, follow_redirects=False)
    assert response.status_code == 303
    assert parse_qs(urlsplit(response.headers["location"]).query)["next"] == [path]
    assert client.get(path, auth=ADMIN).status_code == 401
    assert "www-authenticate" not in response.headers


@pytest.mark.parametrize(
    "path",
    [
        "/admin/rooms/latest-status",
        "/admin/rooms/1/recent-bookings",
        "/admin/rooms/1/qr.pdf",
        "/admin/uploads/missing.png",
    ],
)
def test_data_and_downloads_never_redirect_or_prompt(client, path):
    response = client.get(path, headers={"Accept": "text/html"}, auth=ADMIN)
    assert response.status_code == 401
    assert "www-authenticate" not in response.headers
    assert "location" not in response.headers


def test_session_is_hashed_host_only_secure_and_not_sliding(client, monkeypatch):
    client.base_url = "https://testserver"
    client.headers["Origin"] = "https://testserver"
    now = int(time.time())
    response = login(client, target="/admin/nachrichten")
    assert response.status_code == 303 and response.headers["location"] == "/admin/nachrichten"
    cookies = SimpleCookie()
    for value in response.headers.get_list("set-cookie"):
        cookies.load(value)
    cookie = cookies[auth.ADMIN_COOKIE]
    assert cookie["httponly"] and cookie["secure"] and cookie["samesite"] == "strict"
    assert cookie["path"] == "/" and not cookie["domain"]
    assert not cookie["max-age"] and not cookie["expires"]
    raw = cookie.value
    digest = hashlib.sha256(raw.encode()).hexdigest()
    with db.db_connect() as conn:
        session = dict(conn.execute("SELECT * FROM admin_sessions").fetchone())
    assert session["id_hash"] == digest and raw not in str(session)
    assert now + 8 * 3600 <= session["expires_at"] <= now + 8 * 3600 + 2
    monkeypatch.setattr(auth.time, "time", lambda: now + 600)
    assert client.get("/admin").status_code == 200
    with db.db_connect() as conn:
        assert dict(conn.execute("SELECT * FROM admin_sessions").fetchone()) == session
    monkeypatch.setattr(auth.time, "time", lambda: session["expires_at"])
    assert client.get("/admin").status_code == 401


@pytest.mark.parametrize(
    "target",
    [
        "https://evil.example/admin",
        "//evil.example/admin",
        "/admin/../hilfe",
        "/admin/anmelden",
        "/admin/abmelden",
        "/admin\\evil",
        "/admin\r\nLocation: https://evil.example",
        "/hilfe",
        "/admin#fragment",
    ],
)
def test_login_rejects_unsafe_return_targets(client, target):
    response = login(client, target=target)
    assert response.headers["location"] == "/admin"


def test_login_failure_never_echoes_password_or_leaks_configuration(client, caplog):
    password = "private-wrong-password-123"
    response = login(client, username="<script>bad()</script>", password=password)
    assert response.status_code == 401
    assert "Benutzername oder Passwort ist falsch." in response.text
    assert password not in response.text + caplog.text
    assert '<input type="password" name="password" autocomplete=' in response.text
    assert "&lt;script&gt;" in response.text
    assert auth.ADMIN_COOKIE not in client.cookies


@pytest.mark.parametrize("attack", ["missing", "wrong", "foreign"])
def test_login_csrf(client, attack):
    csrf = token(client.get("/admin/anmelden"))
    data = {"username": ADMIN[0], "password": ADMIN[1], "csrf_token": csrf}
    headers = {}
    if attack == "missing":
        data.pop("csrf_token")
    if attack == "wrong":
        data["csrf_token"] = "wrong"
    if attack == "foreign":
        headers["Origin"] = "https://evil.example"
    assert client.post("/admin/anmelden", data=data, headers=headers).status_code == 403
    with db.db_connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM admin_sessions").fetchone()[0] == 0


def test_login_rate_limit_is_separate_from_resident_submissions(client):
    csrf = token(client.get("/admin/anmelden"))
    for _ in range(10):
        assert (
            client.post(
                "/admin/anmelden",
                data={"username": ADMIN[0], "password": "bad", "csrf_token": csrf},
            ).status_code
            == 401
        )
    denied = client.post(
        "/admin/anmelden", data={"username": ADMIN[0], "password": ADMIN[1], "csrf_token": csrf}
    )
    assert denied.status_code == 429 and int(denied.headers["retry-after"]) > 0
    assert client.post("/r/sauna/submit", data=VALID, follow_redirects=False).status_code == 303


def test_logout_revokes_replays_preserves_reader_and_other_browser(client):
    client.base_url = "https://testserver"
    client.headers["Origin"] = "https://testserver"
    assert grant(client).status_code == 204
    reader = client.cookies.get("raumlog_reader")
    assert login(client).status_code == 303
    old = client.cookies.get(auth.ADMIN_COOKIE)
    other = TestClient(app, base_url="https://testserver", headers={"Origin": "https://testserver"})
    try:
        assert login(other).status_code == 303
        csrf = token(client.get("/admin"))
        assert client.post("/admin/abmelden", data={"csrf_token": "wrong"}).status_code == 403
        response = client.post("/admin/abmelden", data={"csrf_token": csrf}, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/anmelden?abgemeldet=1"
        assert auth.ADMIN_COOKIE not in client.cookies and auth.CSRF_COOKIE not in client.cookies
        assert client.cookies.get("raumlog_reader") == reader
        assert "Du bist abgemeldet." in client.get(response.headers["location"]).text
        assert client.get("/logbuch").status_code == 200
        assert client.get("/admin", auth=AdminSessionAuth(old)).status_code == 401
        assert client.get("/admin", auth=ADMIN).status_code == 401
        assert other.get("/admin").status_code == 200
        with db.db_connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM admin_sessions").fetchone()[0] == 1
    finally:
        other.close()


def test_logout_token_cannot_be_reused_with_another_admin_session(client):
    login(client)
    first = token(client.get("/admin"))
    first_raw = client.cookies.get(auth.ADMIN_COOKIE)
    # Eine erneute Anmeldung rotiert die Sitzung und das CSRF-Token.
    assert login(client).status_code == 303
    assert client.cookies.get(auth.ADMIN_COOKIE) != first_raw
    assert client.get("/admin", auth=AdminSessionAuth(first_raw)).status_code == 401
    client.cookies.set(auth.CSRF_COOKIE, first, domain="testserver.local", path="/admin")
    assert client.post("/admin/abmelden", data={"csrf_token": first}).status_code == 403
    assert client.get("/admin").status_code == 200


@pytest.mark.parametrize("setting", ["ADMIN_USERNAME", "ADMIN_PASSWORD"])
def test_credential_changes_revoke_sessions(client, monkeypatch, setting):
    login(client)
    monkeypatch.setenv(setting, "changed")
    assert client.get("/admin").status_code == 401
    assert client.get("/").status_code == 200


def test_missing_configuration_fails_closed(client, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD")
    assert client.get("/admin/anmelden").status_code == 503
    assert client.get("/admin").status_code == 503
    assert client.get("/hilfe").status_code == 200


@pytest.mark.parametrize(
    "path,current",
    [
        ("/admin", "/admin"),
        ("/admin/nachrichten", "/admin/nachrichten"),
        ("/admin/raumzugaenge", "/admin/raumzugaenge"),
        ("/admin/session/1", "/admin"),
        ("/admin/logbuch", "/admin"),
    ],
)
def test_admin_pages_share_navigation_and_logout(client, path, current):
    client.post("/r/sauna/submit", data=VALID)
    login(client)
    response = client.get(path)
    assert response.status_code == 200
    assert 'aria-label="Verwaltungsnavigation"' in response.text
    assert 'aria-label="Hauptnavigation"' not in response.text
    assert f'href="{current}" aria-current="page"' in response.text
    assert 'action="/admin/abmelden"' in response.text and ">Abmelden</button>" in response.text
    assert 'class="admin-header-link" href="/">Zur App</a>' in response.text
