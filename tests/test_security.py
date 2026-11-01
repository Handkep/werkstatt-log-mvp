import re

import pytest

from app import auth, db
from tests.conftest import ADMIN, VALID


def csrf(client, session_id=1):
    response = client.get(f"/admin/session/{session_id}", auth=ADMIN)
    assert response.status_code == 200
    return re.search(r'name="csrf_token" value="([^"]+)"', response.text)[1]


@pytest.mark.parametrize("path", ["/", "/r/werkstatt", "/hilfe", "/datenschutz"])
def test_public_forms(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert "no-store" in response.headers["cache-control"]


@pytest.mark.parametrize(
    "path",
    [
        "/admin",
        "/admin/nachrichten",
        "/logbuch",
        "/admin/session/1",
        "/uploads/unknown.png",
    ],
)
def test_protected_endpoints(client, path):
    expected = 401 if path.startswith("/admin") else 403
    assert client.get(path).status_code == expected
    assert client.get(path, auth=("wrong", "wrong")).status_code == expected
    response = client.get(path, auth=ADMIN)
    assert response.status_code in {200, 404}
    assert "no-store" in response.headers["cache-control"]


def test_unconfigured_admin_is_closed(client, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD")
    assert client.get("/admin").status_code == 503
    assert client.get("/hilfe").status_code == 200


def test_no_public_notes_or_usage_leak(client):
    payload = '<script>alert("x")</script>'
    assert (
        client.post("/r/werkstatt/submit", data={**VALID, "person_name": payload}).status_code
        == 200
    )
    client.post("/hilfe", data={"person_name": "SECRET-NAME", "note": payload})
    for url in ["/", "/r/werkstatt", "/thanks", "/hilfe", "/datenschutz", "/openapi.json"]:
        response = client.get(url)
        assert "SECRET-NAME" not in response.text
        assert payload not in response.text
    for url in ["/logbuch", "/admin", "/admin/nachrichten", "/admin/session/1"]:
        response = client.get(url, auth=ADMIN)
        assert payload not in response.text
        assert "&lt;script&gt;" in response.text


@pytest.mark.parametrize("attack", ["missing", "wrong", "no-cookie", "forged", "expired", "future"])
def test_csrf_attempts(client, monkeypatch, attack):
    client.post("/r/werkstatt/submit", data=VALID)
    token = csrf(client)
    data = {"csrf_token": token}
    if attack == "missing":
        data = {}
    if attack == "wrong":
        data["csrf_token"] = "wrong"
    if attack == "no-cookie":
        client.cookies.clear()
    if attack == "forged":
        data["csrf_token"] = "1." + "a" * 64 + "." + "b" * 64
        client.cookies.set(auth.CSRF_COOKIE, data["csrf_token"], path="/admin")
    if attack == "expired":
        monkeypatch.setattr(auth.time, "time", lambda: int(token.split(".")[0]) + 3601)
    if attack == "future":
        monkeypatch.setattr(auth.time, "time", lambda: int(token.split(".")[0]) - 1)
    response = client.post(
        "/admin/session/1/delete", auth=ADMIN, data=data, headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403
    with db.db_connect() as conn:
        assert conn.execute("SELECT deleted_at FROM usage_sessions").fetchone()[0] is None


def test_valid_csrf_and_soft_delete(client):
    client.post("/r/werkstatt/submit", data=VALID)
    token = csrf(client)
    response = client.post(
        "/admin/session/1/delete", auth=ADMIN, data={"csrf_token": token}, follow_redirects=False
    )
    assert response.status_code == 303
    assert client.get("/admin/session/1", auth=ADMIN).status_code == 404
    assert "Test Person" not in client.get("/logbuch", auth=ADMIN).text
    with db.db_connect() as conn:
        assert conn.execute("SELECT deleted_at FROM usage_sessions").fetchone()[0]
    assert (
        client.post("/admin/session/1/delete", auth=ADMIN, data={"csrf_token": token}).status_code
        == 404
    )


def test_csrf_credential_rotation_and_cookie_attributes(client, monkeypatch):
    client.post("/r/werkstatt/submit", data=VALID)
    token = csrf(client)
    assert auth.valid_csrf_token(token)
    monkeypatch.setenv("ADMIN_PASSWORD", "rotated")
    assert not auth.valid_csrf_token(token)


def test_hosts_headers_and_asset_cache(client):
    assert client.get("/", headers={"host": "attacker.example"}).status_code == 400
    response = client.get("/")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert re.search(r"/static/theme.js\?v=[0-9a-f]{12}", response.text)
    assert client.get("/static/styles/viewer.css").headers["cache-control"] == "no-cache"


def test_csrf_cookie_https_and_nonce_csp(client):
    client.post("/r/werkstatt/submit", data=VALID)
    response = client.get("https://testserver/admin/session/1", auth=ADMIN)
    cookie = response.headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert "domain=" not in cookie
    nonce = re.search(r'<script nonce="([^"]+)"', response.text)[1]
    assert f"'nonce-{nonce}'" in response.headers["content-security-policy"]
    assert "script-src 'self' 'unsafe-inline'" not in response.headers["content-security-policy"]
    assert response.headers["strict-transport-security"] == "max-age=31536000"


def test_unauthenticated_mutation_does_not_fall_back(client):
    response = client.post("/admin/session/1/delete", data={"csrf_token": "x"})
    assert response.status_code == 401


def test_openapi_developer_ui_assets_remain_allowed(client):
    for path in ("/docs", "/redoc"):
        response = client.get(path)
        assert response.status_code == 200
        policy = response.headers["content-security-policy"]
        assert "https://cdn.jsdelivr.net" in policy
        assert "'unsafe-inline'" in policy
    assert "script-src 'self' 'nonce-" in client.get("/").headers["content-security-policy"]
