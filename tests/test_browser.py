"""Echte Browser-Regressionen; optional über requirements-browser.txt installieren."""

import io
import shutil
import socket
import threading
import time

import pytest
import uvicorn
from PIL import Image

playwright = pytest.importorskip("playwright.sync_api")

from app.main import app  # noqa: E402
from tests.conftest import ADMIN, VALID  # noqa: E402


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as runtime:
        executable = shutil.which("chromium") or shutil.which("chromium-browser")
        browser = runtime.chromium.launch(executable_path=executable, headless=True)
        yield browser
        browser.close()


@pytest.fixture
def live_url(client):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(
            uvicorn.Config(app, log_level="warning", access_log=False, proxy_headers=False)
        )
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        deadline = time.monotonic() + 5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            assert not thread.is_alive()


@pytest.fixture
def page(browser, live_url):
    context = browser.new_context(http_credentials={"username": ADMIN[0], "password": ADMIN[1]})
    page = context.new_page()
    page.set_default_timeout(5000)
    yield page
    context.close()


def fill_usage(page):
    page.locator('[name="person_name"]').fill("Browser Person")
    page.locator('[name="house_number"]').fill("12")
    page.get_by_text("Sauber", exact=True).click()


def test_personal_data_saved_while_typing_and_can_be_removed(page, live_url, browser):
    page.goto(live_url + "/r/sauna")
    remember = page.locator("footer [data-remember-enabled]")
    assert remember.is_checked()
    assert remember.evaluate("el => el.form.id === 'room-usage-form' && !el.closest('form')")
    fill_usage(page)
    page.locator('[name="house_number"]').fill("0012")
    page.get_by_text("GH", exact=True).click()
    assert page.evaluate("localStorage.getItem('usage_person_name')") == "Browser Person"
    assert page.evaluate("localStorage.getItem('usage_house_number')") == "0012"
    page.goto(live_url + "/r/werkstatt")
    assert page.locator('[name="person_name"]').input_value() == "Browser Person"
    assert page.locator('[name="house_group"][value="GH"]').is_checked()
    restored = browser.new_context(storage_state=page.context.storage_state())
    try:
        other = restored.new_page()
        other.goto(live_url + "/r/sauna")
        assert other.locator('[name="person_name"]').input_value() == "Browser Person"
        assert other.locator('[name="house_number"]').input_value() == "0012"
    finally:
        restored.close()
    page.locator("[data-forget-personal]").click()
    assert page.url == live_url + "/r/werkstatt"
    assert page.locator('[name="person_name"]').input_value() == ""
    assert page.locator('[name="house_number"]').input_value() == ""
    assert page.locator('[name="house_group"][value="TH"]').is_checked()
    assert page.evaluate("localStorage.getItem('usage_person_name')") is None
    assert page.evaluate("localStorage.getItem('usage_remember')") == "no"
    page.reload()
    assert not page.locator("[data-remember-enabled]").is_checked()
    assert page.locator('[name="person_name"]').input_value() == ""
    page.locator('[name="person_name"]').fill("Not remembered")
    assert page.evaluate("localStorage.getItem('usage_person_name')") is None


def test_remember_toggle_and_anonymous_help_preserve_profile(page, live_url, client):
    from app import db

    page.goto(live_url + "/r/sauna")
    fill_usage(page)
    page.locator("[data-remember-enabled]").uncheck()
    page.reload()
    assert not page.locator("[data-remember-enabled]").is_checked()
    assert page.evaluate("localStorage.getItem('usage_person_name')") is None
    page.locator('[name="person_name"]').fill("Profile Person")
    page.locator("[data-remember-enabled]").check()
    page.goto(live_url + "/hilfe")
    assert page.locator("footer [data-remember-enabled]").count() == 0
    assert page.locator('[name="person_name"]').input_value() == "Profile Person"
    page.locator('[name="person_name"]').fill("")
    page.locator('[name="note"]').fill("Anonymous question")
    page.get_by_role("button", name="Nachricht senden", exact=True).click()
    page.wait_for_url("**/hilfe?gespeichert=1")
    assert page.evaluate("localStorage.getItem('usage_person_name')") == "Profile Person"
    assert "Anonymous question" not in page.evaluate("JSON.stringify(localStorage)")
    with db.db_connect() as conn:
        assert conn.execute("SELECT person_name FROM general_notes").fetchone()[0] == ""


def test_server_validation_values_override_local_profile(page, live_url, client):
    page.goto(live_url)
    page.evaluate("localStorage.setItem('usage_person_name', 'Saved Profile')")
    response = client.post(
        "/r/sauna/submit",
        data={**VALID, "person_name": "Submitted Person", "house_group": "GH", "condition": "bad"},
    )
    assert response.status_code == 400
    page.route(
        "**/r/sauna?validation=1",
        lambda route: route.fulfill(status=400, content_type="text/html", body=response.text),
    )
    page.goto(live_url + "/r/sauna?validation=1")
    assert page.locator('[name="person_name"]').input_value() == "Submitted Person"
    assert page.locator('[name="house_group"][value="GH"]').is_checked()
    assert page.evaluate("localStorage.getItem('usage_person_name')") == "Saved Profile"
    help_error = client.post("/hilfe", data={"person_name": "", "note": "  "})
    page.route(
        "**/hilfe?validation=1",
        lambda route: route.fulfill(status=400, content_type="text/html", body=help_error.text),
    )
    page.goto(live_url + "/hilfe?validation=1")
    assert page.locator('[name="person_name"]').input_value() == ""


def test_blocked_storage_does_not_break_ui(page, live_url):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.add_init_script(
        "Object.defineProperty(window, 'localStorage', {get() { throw new Error('blocked'); }});"
    )
    page.goto(live_url + "/r/sauna")
    page.locator(".theme-toggle").click()
    assert page.locator("html").get_attribute("data-theme") == "dark"
    fill_usage(page)
    assert (
        "Speichern auf diesem Gerät ist nicht verfügbar"
        in page.locator("[data-remember-status]").inner_text()
    )
    page.get_by_role("button", name="Nutzung speichern", exact=True).click()
    page.wait_for_url("**/thanks?**")
    assert errors == []


def test_preview_urls_released_on_error_replacement_and_pagehide(page, live_url):
    page.add_init_script("""window.previewUrls = new Set();
    const create = URL.createObjectURL.bind(URL), revoke = URL.revokeObjectURL.bind(URL);
    URL.createObjectURL = (file) => {const url = create(file); previewUrls.add(url); return url;};
    URL.revokeObjectURL = (url) => {previewUrls.delete(url); revoke(url);};""")
    page.goto(live_url + "/r/sauna")
    field = page.locator(".file-input")
    field.set_input_files({"name": "broken.png", "mimeType": "image/png", "buffer": b"bad-image"})
    page.wait_for_function("() => previewUrls.size === 0")
    assert page.locator(".file-preview-item").count() == 1
    field.set_input_files(
        {"name": "other.png", "mimeType": "image/png", "buffer": b"other-bad-image"}
    )
    page.wait_for_function("() => previewUrls.size === 0")
    page.locator(".file-preview-remove").click()
    assert page.locator(".file-preview-item").count() == 0
    page.evaluate("window.dispatchEvent(new Event('pagehide'))")
    assert page.evaluate("previewUrls.size") == 0


def test_viewer_keyboard_focus_and_screenreader_status(page, live_url, client):
    out = io.BytesIO()
    Image.new("RGB", (24, 24), "red").save(out, "PNG")
    response = client.post(
        "/r/sauna/submit",
        data=VALID,
        files=[("images", ("a.png", out.getvalue())), ("images", ("b.png", out.getvalue()))],
    )
    assert response.status_code == 200
    from tests.test_capabilities import token

    page.goto(live_url + "/r/werkstatt#access=" + token("werkstatt"))
    page.get_by_role("link", name="QR-PDF herunterladen", exact=True).wait_for()
    page.goto(live_url + "/logbuch")
    trigger = page.locator("[data-viewer-images]").first
    trigger.focus()
    page.keyboard.press("Enter")
    close = page.locator(".image-viewer-close")
    assert close.evaluate("el => el === document.activeElement")
    assert page.locator("main").evaluate("el => el.inert")
    page.keyboard.press("Shift+Tab")
    assert page.locator("[data-viewer-next]").evaluate("el => el === document.activeElement")
    page.keyboard.press("Tab")
    assert close.evaluate("el => el === document.activeElement")
    page.keyboard.press("ArrowRight")
    assert page.locator("[data-viewer-count]").inner_text() == "2 von 2"
    assert page.locator("[data-viewer-count]").get_attribute("aria-live") == "polite"
    page.keyboard.press("Escape")
    assert page.locator("[data-image-viewer]").is_hidden()
    assert trigger.evaluate("el => el === document.activeElement")
    assert not page.locator("main").evaluate("el => el.inert")
    page.screenshot(path="/tmp/raumlog-desktop.png", full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(live_url + "/r/sauna")
    page.screenshot(path="/tmp/raumlog-mobile.png", full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_admin_delete_form_confirmation_and_csrf_work_in_browser(page, live_url, client):
    client.post("/r/sauna/submit", data=VALID)
    page.goto(live_url + "/admin/session/1")
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Eintrag löschen", exact=True).click()
    page.wait_for_url(live_url + "/admin")
    assert client.get("/admin/session/1", auth=ADMIN).status_code == 404


def test_room_qr_icon_downloads_directly_without_opening_room(page, live_url):
    from tests.test_capabilities import token

    page.goto(live_url + "/r/werkstatt#access=" + token("werkstatt"))
    page.get_by_role("link", name="QR-PDF herunterladen", exact=True).wait_for()
    page.goto(live_url)
    page.evaluate("document.documentElement.dataset.theme = 'dark'")
    link = page.get_by_role("link", name="QR-PDF für Werkstatt herunterladen", exact=True)
    with page.expect_download() as download:
        link.click()
    assert download.value.suggested_filename == "zelter5-qr-werkstatt.pdf"
    assert page.url == live_url + "/"
    link.focus()
    with page.expect_download() as keyboard_download:
        page.keyboard.press("Enter")
    assert keyboard_download.value.suggested_filename == "zelter5-qr-werkstatt.pdf"
    assert page.url == live_url + "/"
    page.screenshot(path="/tmp/raumlog-qr-cards.png", full_page=True)
    page.get_by_role("heading", name="Werkstatt", exact=True).click()
    page.wait_for_url(live_url + "/r/werkstatt")
