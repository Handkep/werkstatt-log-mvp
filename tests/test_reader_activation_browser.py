"""QR-Aktivierung und Navigation im frischen Browser mit isolierten Testdaten."""

from urllib.parse import urlsplit

import pytest

from app.capabilities import READER_COOKIE, room_qr_url
from tests import test_browser, test_capability_browser
from tests.test_capabilities import room

browser = test_browser.browser
secure_url = test_capability_browser.secure_url
reader_page = test_capability_browser.reader_page


def queued_scan(page):
    pending = []
    page.route("**/r/werkstatt/access", lambda route: pending.append(route))
    url = room_qr_url(room("werkstatt"))
    page.goto(url)
    page.get_by_text("Zugang wird aktiviert …", exact=True).wait_for()
    assert len(pending) == 1
    assert not urlsplit(page.url).fragment
    return pending[0], url


@pytest.mark.parametrize("keyboard", [False, True])
def test_immediate_logbook_navigation_waits_for_verified_cookie(reader_page, secure_url, keyboard):
    page = reader_page
    page.set_viewport_size({"width": 390, "height": 844})
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    pending, qr_url = queued_scan(page)
    link = page.get_by_role("link", name="Logbuch", exact=True)
    if keyboard:
        link.press("Enter")
    else:
        link.click()
    assert urlsplit(page.url).path == "/r/werkstatt"
    assert page.locator(".site-nav").get_attribute("aria-busy") == "true"
    assert all(cookie["name"] != READER_COOKIE for cookie in page.context.cookies())
    pending.continue_()
    page.wait_for_url(secure_url + "/logbuch")
    assert page.get_by_role("heading", name="Logbuch", exact=True).is_visible()
    cookie = next(cookie for cookie in page.context.cookies() if cookie["name"] == READER_COOKIE)
    assert cookie["secure"] and cookie["httpOnly"] and cookie["sameSite"] == "Lax"
    assert cookie["path"] == "/"
    assert secure_url + "/rooms/latest-status" in requests
    raw_token = qr_url.split("#access=")[1]
    assert all(raw_token not in url for url in requests)
    assert raw_token not in page.evaluate("JSON.stringify(localStorage)")
    page.goto(secure_url + "/r/sauna")
    page.get_by_role("link", name="QR-PDF herunterladen", exact=True).wait_for()
    page.get_by_role("link", name="Logbuch", exact=True).click()
    page.wait_for_url(secure_url + "/logbuch")
    page.get_by_role("heading", name="Logbuch", exact=True).wait_for()
    page.reload()
    assert page.get_by_role("heading", name="Logbuch", exact=True).is_visible()


def test_multiple_clicks_keep_latest_target(reader_page, secure_url):
    page = reader_page
    pending, _ = queued_scan(page)
    page.get_by_role("link", name="Logbuch", exact=True).click()
    page.get_by_role("link", name="Hilfe & Infos", exact=True).click()
    assert urlsplit(page.url).path == "/r/werkstatt"
    pending.continue_()
    page.wait_for_url(secure_url + "/hilfe")
    assert page.get_by_role("heading", name="Hilfe & Infos", exact=True).is_visible()


def test_navigation_also_waits_for_confirmation(reader_page, secure_url):
    page = reader_page
    pending = []
    page.route("**/rooms/latest-status", lambda route: pending.append(route))
    page.goto(room_qr_url(room("werkstatt")))
    page.wait_for_function(
        "document.querySelector('.site-nav').getAttribute('aria-busy') === 'true'"
    )
    page.get_by_role("link", name="Logbuch", exact=True).click()
    assert urlsplit(page.url).path == "/r/werkstatt"
    assert any(cookie["name"] == READER_COOKIE for cookie in page.context.cookies())
    assert len(pending) == 1
    pending[0].continue_()
    page.wait_for_url(secure_url + "/logbuch")


def test_missing_cookie_has_clear_error_and_releases_navigation(reader_page, secure_url):
    page = reader_page
    # Erfolgsantwort ohne angenommenes Set-Cookie simuliert Cookiesperre/Filter.
    page.route("**/r/werkstatt/access", lambda route: route.fulfill(status=204))
    page.goto(room_qr_url(room("werkstatt")))
    page.get_by_text(
        "Der Zugang konnte in diesem Browser nicht gespeichert werden.", exact=False
    ).wait_for()
    assert urlsplit(page.url).path == "/r/werkstatt"
    assert page.locator(".site-nav").get_attribute("aria-busy") is None
    page.get_by_role("link", name="Hilfe & Infos", exact=True).click()
    page.wait_for_url(secure_url + "/hilfe")


def test_invalid_token_is_not_misreported_as_expired(reader_page, secure_url):
    page = reader_page
    page.goto(secure_url + "/r/werkstatt#access=" + "A" * 43)
    page.get_by_text("Die Zugangsprüfung wurde abgelehnt.", exact=False).wait_for()
    assert "abgelaufen" not in page.locator("[data-room-access-status]").inner_text()
    assert not urlsplit(page.url).fragment
    assert page.locator(".site-nav").get_attribute("aria-busy") is None


def test_network_failure_releases_navigation(reader_page, secure_url):
    page = reader_page
    page.route("**/r/werkstatt/access", lambda route: route.abort("connectionfailed"))
    page.goto(room_qr_url(room("werkstatt")))
    page.get_by_text(
        "Die Verbindung zur Zugangsprüfung ist fehlgeschlagen.", exact=False
    ).wait_for()
    assert page.locator(".site-nav").get_attribute("aria-busy") is None
    page.get_by_role("link", name="Hilfe & Infos", exact=True).click()
    page.wait_for_url(secure_url + "/hilfe")


def test_timeout_discards_target_and_releases_navigation(reader_page, secure_url):
    page = reader_page
    page.clock.install()
    pending, _ = queued_scan(page)
    page.get_by_role("link", name="Logbuch", exact=True).click()
    page.clock.fast_forward(15000)
    page.get_by_text("Die Zugangsprüfung dauert zu lange.", exact=False).wait_for()
    assert urlsplit(page.url).path == "/r/werkstatt"
    assert page.locator(".site-nav").get_attribute("aria-busy") is None
    pending.abort()
    page.get_by_role("link", name="Hilfe & Infos", exact=True).click()
    page.wait_for_url(secure_url + "/hilfe")
