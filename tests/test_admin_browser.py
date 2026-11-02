"""Verwaltungsoberfläche und Logout im Browser mit temporären Testdaten."""

import pytest

from tests import test_browser
from tests.conftest import ADMIN, VALID
from tests.test_capabilities import token

browser = test_browser.browser
live_url = test_browser.live_url
page = test_browser.page


def test_public_admin_button_login_and_logout_across_tabs(page, live_url):
    page.goto(live_url + "/r/werkstatt#access=" + token("werkstatt"))
    page.get_by_role("link", name="QR-PDF herunterladen", exact=True).wait_for()
    test_browser.fill_usage(page)
    page.get_by_role("link", name="Verwaltung", exact=True).click()
    page.get_by_label("Benutzername", exact=True).fill(ADMIN[0])
    page.get_by_label("Passwort", exact=True).fill("wrong-private-password")
    page.get_by_role("button", name="Anmelden", exact=True).click()
    assert "Benutzername oder Passwort ist falsch." in page.get_by_role("alert").inner_text()
    assert page.get_by_label("Passwort", exact=True).input_value() == ""
    page.get_by_label("Passwort", exact=True).fill(ADMIN[1])
    page.get_by_role("button", name="Anmelden", exact=True).click()
    page.wait_for_url(live_url + "/admin")
    other = page.context.new_page()
    try:
        other.goto(live_url + "/admin/nachrichten")
        assert other.get_by_role("heading", name="Nachrichten", exact=True).is_visible()
        page.get_by_role("button", name="Abmelden", exact=True).click()
        page.get_by_role("status").get_by_text("Du bist abgemeldet.", exact=True).wait_for()
        other.reload()
        other.get_by_role("heading", name="Anmelden", exact=True).wait_for()
        assert page.evaluate("localStorage.getItem('usage_person_name')") == "Browser Person"
        assert page.request.get(live_url + "/admin/rooms/latest-status").status == 401
        assert page.request.get(live_url + "/logbuch").status == 200
        page.get_by_role("link", name="Zur App", exact=True).click()
        nav = page.get_by_role("navigation", name="Hauptnavigation", exact=True)
        assert [text.strip() for text in nav.get_by_role("link").all_text_contents()] == [
            "Räume",
            "Logbuch",
            "Hilfe & Infos",
        ]
    finally:
        other.close()


@pytest.mark.parametrize("width", [390, 768, 1280])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_admin_pages_and_login_fit_with_keyboard_navigation(
    page, live_url, client, width, theme, tmp_path
):
    client.post("/r/sauna/submit", data=VALID)
    page.set_viewport_size({"width": width, "height": 900})
    page.emulate_media(reduced_motion="reduce")
    page.add_init_script(f"localStorage.setItem('theme', '{theme}')")
    page.goto(live_url + "/admin")
    page.get_by_label("Benutzername", exact=True).wait_for()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(tmp_path / f"login-{width}-{theme}.png"), full_page=True)
    page.get_by_label("Benutzername", exact=True).fill(ADMIN[0])
    page.get_by_label("Passwort", exact=True).fill(ADMIN[1])
    page.get_by_role("button", name="Anmelden", exact=True).press("Enter")
    page.wait_for_url(live_url + "/admin")
    for path, current in [
        ("/admin", "Einträge"),
        ("/admin/nachrichten", "Nachrichten"),
        ("/admin/raumzugaenge", "QR-Zugänge"),
        ("/admin/session/1", "Einträge"),
    ]:
        page.goto(live_url + path)
        nav = page.get_by_role("navigation", name="Verwaltungsnavigation", exact=True)
        assert nav.get_by_role("link").all_text_contents() == [
            "Einträge",
            "Nachrichten",
            "QR-Zugänge",
        ]
        assert (
            nav.get_by_role("link", name=current, exact=True).get_attribute("aria-current")
            == "page"
        )
        assert page.get_by_role("navigation", name="Hauptnavigation").count() == 0
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        for control in page.locator(".admin-header a, .admin-header button").all():
            box = control.bounding_box()
            assert box["x"] >= 0 and box["x"] + box["width"] <= width
        page.screenshot(
            path=str(tmp_path / f"admin-{path.rsplit('/', 1)[-1]}-{width}-{theme}.png"),
            full_page=True,
        )
    logout = page.get_by_role("button", name="Abmelden", exact=True)
    logout.focus()
    assert logout.evaluate("el => getComputedStyle(el).outlineStyle") == "solid"
    page.keyboard.press("Enter")
    page.get_by_text("Du bist abgemeldet.", exact=True).wait_for()
