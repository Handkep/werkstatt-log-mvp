"""Capability-Fluss im echten HTTPS-Browser ohne Bewohner-Anmeldung."""

import io
import socket
import subprocess
import threading
import time

import pytest
import uvicorn
from PIL import Image

from app.capabilities import READER_COOKIE, room_qr_url
from app.main import app
from tests import test_browser
from tests.conftest import VALID
from tests.test_capabilities import room, rotation

browser = test_browser.browser
live_url = test_browser.live_url


@pytest.fixture
def secure_url(client, tmp_path, monkeypatch):
    certificate, key = tmp_path / "test.crt", tmp_path / "test.key"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-out",
            str(certificate),
            "-keyout",
            str(key),
        ],
        capture_output=True,
        check=True,
        timeout=15,
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        base = f"https://127.0.0.1:{sock.getsockname()[1]}"
        monkeypatch.setenv("PUBLIC_BASE_URL", base)
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                log_level="warning",
                access_log=False,
                proxy_headers=False,
                ssl_certfile=str(certificate),
                ssl_keyfile=str(key),
            )
        )
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        deadline = time.monotonic() + 5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        try:
            yield base
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            assert not thread.is_alive()


@pytest.fixture
def reader_page(browser, secure_url):
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()
    page.set_default_timeout(5000)
    yield page
    context.close()


def scan(page, slug="sauna"):
    url = room_qr_url(room(slug))
    page.goto(url)
    page.get_by_role("link", name="QR-PDF herunterladen", exact=True).wait_for()
    assert "#" not in page.url
    return url


def test_scan_reads_images_and_prints_pdf_without_admin(reader_page, secure_url, client):
    page = reader_page
    output = io.BytesIO()
    with Image.new("RGB", (24, 24), "red") as image:
        image.save(output, "PNG")
    client.post(
        "/r/sauna/submit",
        data={**VALID, "person_name": "SAUNA-READER"},
        files={"images": ("test.png", output.getvalue())},
    )
    client.post("/r/werkstatt/submit", data={**VALID, "person_name": "WORKSHOP-HIDDEN"})
    requests = []
    page.on("request", lambda request: requests.append(request))
    qr_url = scan(page)
    raw_token = qr_url.split("#access=")[1]
    assert all(raw_token not in request.url for request in requests)
    assert all("authorization" not in request.headers for request in requests)
    assert raw_token not in page.evaluate("JSON.stringify(localStorage)")
    cookie = next(cookie for cookie in page.context.cookies() if cookie["name"] == READER_COOKIE)
    assert cookie["secure"] and cookie["httpOnly"] and cookie["sameSite"] == "Lax"
    for _ in range(2):
        with page.expect_download() as download:
            page.get_by_role("link", name="QR-PDF herunterladen", exact=True).click()
        assert download.value.suggested_filename == "zelter5-qr-sauna.pdf"
    page.get_by_role("link", name="Alle Buchungen anzeigen").click()
    assert "SAUNA-READER" in page.locator("body").inner_text()
    assert "WORKSHOP-HIDDEN" not in page.locator("body").inner_text()
    page.get_by_role("link", name="Alle Räume", exact=True).click()
    assert "WORKSHOP-HIDDEN" in page.locator("body").inner_text()
    page.locator("[data-viewer-images]").first.click()
    page.wait_for_function(
        "() => document.querySelector('[data-viewer-image]').naturalWidth === 24"
    )
    page.keyboard.press("Escape")
    assert page.request.get(secure_url + "/r/werkstatt/qr.pdf").status == 200
    page.goto(secure_url + "/r/sauna")
    page.screenshot(path="/tmp/raumlog-reader-form.png", full_page=True)


def test_global_session_and_global_rotation_in_browser(reader_page, secure_url, client):
    page = reader_page
    old_url = scan(page)
    original_cookie = next(
        cookie["value"] for cookie in page.context.cookies() if cookie["name"] == READER_COOKIE
    )
    scan(page, "werkstatt")
    assert (
        next(
            cookie["value"] for cookie in page.context.cookies() if cookie["name"] == READER_COOKIE
        )
        == original_cookie
    )
    assert rotation(client).status_code == 303
    page.goto(secure_url + "/r/sauna")
    assert page.get_by_role("link", name="QR-PDF herunterladen", exact=True).count() == 0
    page.goto(old_url)
    page.get_by_text("Dieser Raumzugang ist ungültig oder abgelaufen.", exact=False).wait_for()
    assert "#" not in page.url
    page.goto(secure_url + "/r/werkstatt")
    assert page.get_by_role("link", name="QR-PDF herunterladen", exact=True).count() == 0
    scan(page)


def test_admin_can_bootstrap_pdf_without_reader_session(browser, secure_url):
    context = browser.new_context(ignore_https_errors=True)
    try:
        page = context.new_page()
        test_browser.login_admin(page, secure_url, "/admin/raumzugaenge")
        with page.expect_download() as download:
            page.get_by_role("link", name="QR-PDF herunterladen", exact=True).first.click()
        assert download.value.suggested_filename == "zelter5-qr-werkstatt.pdf"
        page.evaluate(
            "Object.defineProperty(navigator, 'clipboard', {value: {writeText: async value => {window.adminCopiedLink = value;}}})"
        )
        page.get_by_role("button", name="Zugangslink kopieren", exact=True).first.click()
        page.get_by_text("Zugangslink kopiert.", exact=True).wait_for()
        assert page.locator("[data-copied-icon]").first.is_visible()
        assert "#access=" in page.evaluate("window.adminCopiedLink")
        assert all(cookie["name"] != READER_COOKIE for cookie in context.cookies())
    finally:
        context.close()


def test_persistent_reader_cookie_works_on_localhost_http(browser, live_url, monkeypatch):
    base = live_url.replace("127.0.0.1", "localhost")
    monkeypatch.setenv("PUBLIC_BASE_URL", base)
    context = browser.new_context()
    try:
        page = context.new_page()
        page.set_default_timeout(5000)
        scan(page)
        assert page.url.startswith(base)
        cookie = next(cookie for cookie in context.cookies() if cookie["name"] == READER_COOKIE)
        assert not cookie["secure"] and cookie["httpOnly"]
        with page.expect_download() as download:
            page.get_by_role("link", name="QR-PDF herunterladen", exact=True).click()
        assert download.value.suggested_filename == "zelter5-qr-sauna.pdf"
    finally:
        context.close()


def test_copy_link_is_explicit_and_opens_global_access(reader_page, secure_url, browser):
    page = reader_page
    scan(page, "werkstatt")
    page.goto(secure_url + "/r/dachterrasse")
    from tests.test_capabilities import token

    assert token("dachterrasse") not in page.content()
    requested = []
    page.on("request", lambda request: requested.append(request.url))
    page.evaluate(
        "Object.defineProperty(navigator, 'clipboard', {value: {writeText: async (value) => {window.copiedAccessLink = value;}}})"
    )
    assert not any("/access-link" in url for url in requested)
    page.get_by_role("button", name="Zugangslink kopieren", exact=True).click()
    page.get_by_text("Zugangslink kopiert.", exact=True).wait_for()
    copied = page.evaluate("window.copiedAccessLink")
    assert copied.endswith("#access=" + token("dachterrasse"))
    assert len([url for url in requested if "/access-link" in url]) == 1
    context = browser.new_context(ignore_https_errors=True)
    try:
        other = context.new_page()
        other.goto(copied)
        other.get_by_role("link", name="QR-PDF herunterladen", exact=True).wait_for()
        assert "#" not in other.url
        other.goto(secure_url + "/r/sauna")
        assert other.get_by_role("link", name="QR-PDF herunterladen", exact=True).is_visible()
    finally:
        context.close()


def test_missing_reader_does_not_trigger_basic_login(reader_page, secure_url):
    page = reader_page
    for path in ("/logbuch", "/r/sauna/qr.pdf", "/uploads/unknown.png"):
        response = page.goto(secure_url + path)
        assert response.status == 403
        assert "www-authenticate" not in response.headers


def test_cookie_restored_after_browser_restart(browser, reader_page, secure_url):
    import time

    page = reader_page
    scan(page, "werkstatt")
    state = page.context.storage_state()
    cookie = next(cookie for cookie in state["cookies"] if cookie["name"] == READER_COOKIE)
    assert cookie["expires"] > time.time() + 364 * 86400
    assert cookie["value"] not in page.evaluate(
        "JSON.stringify(localStorage) + JSON.stringify(sessionStorage)"
    )
    restored = browser.new_context(ignore_https_errors=True, storage_state=state)
    try:
        other = restored.new_page()
        other.goto(secure_url + "/r/sauna")
        assert other.get_by_role("link", name="QR-PDF herunterladen", exact=True).is_visible()
        assert other.request.get(secure_url + "/r/dachterrasse/qr.pdf").status == 200
    finally:
        restored.close()


def test_admin_images_work_without_reader_cookie(browser, secure_url, client):
    output = io.BytesIO()
    with Image.new("RGB", (12, 12), "red") as image:
        image.save(output, "PNG")
    client.post("/r/sauna/submit", data=VALID, files={"images": ("test.png", output.getvalue())})
    context = browser.new_context(ignore_https_errors=True)
    try:
        page = context.new_page()
        test_browser.login_admin(page, secure_url)
        page.locator("[data-viewer-images]").first.click()
        page.wait_for_function(
            "() => document.querySelector('[data-viewer-image]').naturalWidth === 12"
        )
        assert "/admin/uploads/" in page.locator("[data-viewer-image]").get_attribute("src")
        page.goto(secure_url + "/admin/session/1")
        page.wait_for_function("() => document.querySelector('.gallery img').naturalWidth === 12")
        assert all(cookie["name"] != READER_COOKIE for cookie in context.cookies())
    finally:
        context.close()


@pytest.mark.parametrize("width", [320, 390, 430, 1280])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_navigation_and_preview_layout(reader_page, secure_url, client, width, theme):
    page = reader_page
    page.set_viewport_size({"width": width, "height": 850})
    for index in range(4):
        client.post(
            "/r/werkstatt/submit",
            data={**VALID, "person_name": f"Layout Person {index}", "house_number": "12345678"},
        )
    scan(page, "werkstatt")
    page.evaluate(
        "theme => {localStorage.setItem('theme', theme); document.documentElement.dataset.theme = theme;}",
        theme,
    )
    preview = page.locator("[data-room-bookings]")
    page.wait_for_function(
        "() => document.querySelector('[data-room-bookings]').getAttribute('aria-busy') === 'false'"
    )
    assert preview.locator(".mobile-entry-card").count() == 3
    assert "Layout Person 0" not in preview.inner_text()
    nav = page.get_by_role("navigation", name="Hauptnavigation", exact=True)
    assert [link.inner_text().strip() for link in nav.get_by_role("link").all()] == [
        "Alle Räume",
        "Logbuch",
        "Hilfe & Infos",
    ]
    boxes = [link.bounding_box() for link in nav.get_by_role("link").all()]
    assert max(box["width"] for box in boxes) - min(box["width"] for box in boxes) < 1
    assert all(box["height"] >= 44 for box in boxes)
    assert len({round(box["y"]) for box in boxes}) == 1
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    entry = page.get_by_role("link", name="Verwaltung", exact=True)
    assert entry.get_attribute("href") == "/admin"
    entry.press("Enter")
    page.get_by_label("Benutzername", exact=True).wait_for()
    assert "/admin/anmelden?" in page.url
    assert any("/admin" in url for url in requests)
    page.goto(secure_url + "/r/werkstatt")
    page.screenshot(path=f"/tmp/raumlog-navigation-{width}-{theme}.png", full_page=True)
    page.get_by_role("link", name="Alle Buchungen anzeigen", exact=True).click()
    assert page.url.endswith("/logbuch?raum=werkstatt")
    assert page.get_by_role("heading", name="Logbuch", exact=True).is_visible()
    page.get_by_role("link", name="Hilfe & Infos", exact=True).click()
    assert page.get_by_role("heading", name="Hilfe & Infos", exact=True).is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_preview_images_work_after_dynamic_loading(reader_page, secure_url, client):
    output = io.BytesIO()
    with Image.new("RGB", (24, 24), "red") as image:
        image.save(output, "PNG")
    client.post("/r/sauna/submit", data=VALID, files={"images": ("preview.png", output.getvalue())})
    page = reader_page
    scan(page)
    trigger = page.locator("[data-room-bookings] [data-viewer-images]")
    trigger.wait_for()
    trigger.click()
    page.wait_for_function(
        "() => document.querySelector('[data-viewer-image]').naturalWidth === 24"
    )
    assert page.locator("main").evaluate("el => el.inert")
    page.keyboard.press("Escape")
    assert trigger.evaluate("el => document.activeElement === el")
