"""Echter HTTPS-Browser vor simuliertem HTTP-Backend wie bei TLS-Terminierung."""

import pytest

from app import middleware
from app.capabilities import READER_COOKIE
from app.main import app
from tests import test_browser, test_capability_browser
from tests.test_reader_activation_browser import queued_scan

browser = test_browser.browser
secure_url = test_capability_browser.secure_url
reader_page = test_capability_browser.reader_page


@pytest.fixture(autouse=True)
def terminated_backend(monkeypatch):
    hops = []

    async def tls_terminator(scope, receive, send):
        if scope["type"] == "http":
            scope = dict(scope)
            scope["scheme"] = "http"
            scope["client"] = ("10.99.0.5", 9876)
            headers = [(k, v) for k, v in scope["headers"] if not k.startswith(b"x-forwarded-")]
            scope["headers"] = headers + [
                (b"x-forwarded-proto", b"http"),
                (b"x-forwarded-for", b"192.0.2.99"),
                (b"x-forwarded-host", b"evil.example"),
            ]
            hops.append((scope["path"], scope["scheme"], scope["client"][0]))
        await app(scope, receive, send)

    monkeypatch.setattr(test_capability_browser, "app", tls_terminator)
    # Auch bei bereits aufgebautem gemeinsamem Middleware-Stack kein Proxy-Vertrauen.
    protection = app.middleware_stack
    while protection is not None and not isinstance(
        protection, middleware.RequestProtectionMiddleware
    ):
        protection = getattr(protection, "app", None)
    if protection:
        monkeypatch.setattr(protection, "trusted_proxies", [])
    yield hops


def test_scan_then_immediate_logbook_without_trusted_proxy(
    reader_page, secure_url, terminated_backend
):
    page = reader_page
    page.set_viewport_size({"width": 390, "height": 844})
    pending, _ = queued_scan(page)
    page.get_by_role("link", name="Logbuch", exact=True).click()
    assert page.url == secure_url + "/r/werkstatt"
    pending.continue_()
    page.wait_for_url(secure_url + "/logbuch")
    assert page.get_by_role("heading", name="Logbuch", exact=True).is_visible()
    cookie = next(c for c in page.context.cookies() if c["name"] == READER_COOKIE)
    assert cookie["secure"] and cookie["httpOnly"]
    page.goto(secure_url + "/r/sauna")
    page.get_by_role("link", name="QR-PDF herunterladen", exact=True).wait_for()
    page.get_by_role("link", name="Logbuch", exact=True).click()
    page.wait_for_url(secure_url + "/logbuch")
    page.get_by_role("heading", name="Logbuch", exact=True).wait_for()
    page.reload()
    assert page.get_by_role("heading", name="Logbuch", exact=True).is_visible()
    assert any(path.endswith("/access") for path, _, _ in terminated_backend)
    assert all(scheme == "http" and peer == "10.99.0.5" for _, scheme, peer in terminated_backend)


def test_admin_login_logout_secure_cookies_behind_http_backend(reader_page, secure_url):
    page = reader_page
    test_browser.login_admin(page, secure_url)
    assert page.get_by_role("button", name="Abmelden", exact=True).is_visible()
    relevant = [c for c in page.context.cookies() if c["name"] in {"raumlog_admin", "raumlog_csrf"}]
    assert len(relevant) == 2 and all(c["secure"] and c["httpOnly"] for c in relevant)
    page.get_by_role("button", name="Abmelden", exact=True).click()
    page.get_by_text("Du bist abgemeldet.", exact=True).wait_for()
    assert not any(c["name"] == "raumlog_admin" for c in page.context.cookies())
