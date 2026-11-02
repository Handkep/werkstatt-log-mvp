"""Feste öffentliche Außenadresse, ohne Vertrauen in beliebige Proxy-Header."""

from http.cookies import SimpleCookie

import pytest
from fastapi.testclient import TestClient

from app import auth, capabilities, middleware
from app.main import app
from app.utils import configured_public_scheme
from tests.test_capabilities import token


@pytest.mark.parametrize(
    "base,host,scheme",
    [
        ("https://rooms.example", "rooms.example", "https"),
        ("https://rooms.example/base", "rooms.example:443", "https"),
        ("https://rooms.example", "ROOMS.EXAMPLE", "https"),
        ("https://rooms.example:8443", "rooms.example:8443", "https"),
        ("https://rooms.example:8443", "rooms.example", None),
        ("https://rooms.example", "rooms.example:8443", None),
        ("https://rooms.example", "rooms.example:0", None),
        ("http://localhost:9000", "localhost:9000", "http"),
        ("http://localhost:9000", "localhost", None),
        ("https://[::1]:8443", "[::1]:8443", "https"),
        ("https://münchen.example", "xn--mnchen-3ya.example", "https"),
        ("", "rooms.example", None),
    ],
)
def test_public_host_and_port_must_match(monkeypatch, base, host, scheme):
    monkeypatch.setenv("PUBLIC_BASE_URL", base)
    assert configured_public_scheme(host) == scheme


@pytest.mark.parametrize(
    "host",
    [
        "evil.example",
        "rooms.example.evil",
        "rooms.example@evil.example",
        "evil@rooms.example",
        "rooms.example/path",
        "rooms.example?x=1",
        "rooms.example#fragment",
        "rooms.example\\evil",
        "rooms.example\n",
        "rooms.example:not-a-port",
        "rooms.example:65536",
        "[broken",
        "",
    ],
)
def test_unrelated_or_malformed_authority_does_not_inherit_https(monkeypatch, host):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://rooms.example")
    assert configured_public_scheme(host) is None


def without_proxy_trust(monkeypatch):
    protection = app.middleware_stack
    while not isinstance(protection, middleware.RequestProtectionMiddleware):
        protection = protection.app
    monkeypatch.setattr(protection, "trusted_proxies", [])


@pytest.mark.parametrize(
    "forwarded",
    [
        {},
        {
            "X-Forwarded-Proto": "http",
            "X-Forwarded-Host": "evil.example",
            "X-Forwarded-For": "192.0.2.99",
            "Forwarded": "for=192.0.2.99;proto=http;host=evil.example",
        },
    ],
)
def test_canonical_https_drives_csrf_reader_and_hsts_over_internal_http(
    client, monkeypatch, forwarded
):
    without_proxy_trust(monkeypatch)
    with TestClient(app, base_url="http://testserver", client=("10.99.0.5", 9876)) as proxy:
        response = proxy.get("/admin/anmelden", headers=forwarded)
        cookies = SimpleCookie()
        cookies.load(response.headers["set-cookie"])
        csrf = cookies[auth.CSRF_COOKIE]
        assert csrf["secure"] and csrf["httponly"] and csrf["samesite"] == "strict"
        assert "Strict-Transport-Security" in response.headers
        assert proxy.get("/logbuch", headers=forwarded).status_code == 403
        response = proxy.post(
            "/r/werkstatt/access",
            json={"token": token("werkstatt")},
            headers={**forwarded, "Origin": "https://testserver"},
        )
        assert response.status_code == 204
        cookies.load(response.headers["set-cookie"])
        reader = cookies[capabilities.READER_COOKIE]
        assert reader["secure"] and reader["httponly"] and reader["samesite"] == "lax"
        assert reader["path"] == "/" and not reader["domain"]
        assert proxy.get("https://testserver/logbuch", headers=forwarded).status_code == 200


@pytest.mark.parametrize(
    "origin,host",
    [
        ("http://testserver", "testserver"),
        ("https://evil.example", "testserver"),
        ("https://testserver:444", "testserver"),
        ("https://testserver:0", "testserver"),
        ("https://testserver", "testserver:8443"),
        ("https://localhost", "localhost"),
    ],
)
def test_forged_forwarding_cannot_override_public_origin(client, monkeypatch, origin, host):
    without_proxy_trust(monkeypatch)
    with TestClient(app, base_url="http://testserver", client=("10.99.0.5", 9876)) as proxy:
        response = proxy.post(
            "/r/werkstatt/access",
            json={"token": token("werkstatt")},
            headers={
                "Host": host,
                "Origin": origin,
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "testserver",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        assert response.status_code == 403
        assert capabilities.READER_COOKIE not in response.cookies


def test_no_public_url_keeps_loopback_http_and_http_setting_does_not_downgrade_tls(
    client, monkeypatch
):
    without_proxy_trust(monkeypatch)
    monkeypatch.delenv("PUBLIC_BASE_URL")
    with TestClient(
        app, base_url="http://localhost", headers={"Origin": "http://localhost"}
    ) as local:
        response = local.post("/r/werkstatt/access", json={"token": token("werkstatt")})
        assert response.status_code == 204
        cookies = SimpleCookie()
        cookies.load(response.headers["set-cookie"])
        assert not cookies[capabilities.READER_COOKIE]["secure"]
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://testserver")
    response = client.get("/admin/anmelden")
    cookies = SimpleCookie()
    cookies.load(response.headers["set-cookie"])
    assert cookies[auth.CSRF_COOKIE]["secure"]
