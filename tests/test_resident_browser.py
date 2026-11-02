"""Bewohnerabläufe und Darstellung mit echten Browsern und isolierten Testdaten."""

import pytest

from tests import test_browser
from tests.test_capabilities import token
from tests.test_resident_improvements import add_entries

browser = test_browser.browser
live_url = test_browser.live_url
page = test_browser.page


def unlock(page, live_url):
    page.goto(live_url + "/r/werkstatt#access=" + token("werkstatt"))
    page.get_by_role("link", name="QR-PDF herunterladen", exact=True).wait_for()


def test_room_links_work_without_javascript_and_in_new_tab(browser, live_url):
    context = browser.new_context(java_script_enabled=False)
    try:
        page = context.new_page()
        page.goto(live_url)
        link = page.get_by_role("link", name="Werkstatt", exact=True)
        with context.expect_page() as new_page:
            link.click(modifiers=["Control"])
        new_page.value.wait_for_url("**/r/werkstatt")
        link.focus()
        page.keyboard.press("Enter")
        page.wait_for_url("**/r/werkstatt")
        assert page.get_by_role("button", name="Nutzung speichern", exact=True).is_visible()
    finally:
        context.close()


def test_denied_logbook_and_help_anchor(page, live_url):
    response = page.goto(live_url + "/logbuch")
    assert response.status == 403
    assert page.get_by_role("navigation", name="Hauptnavigation").is_visible()
    page.get_by_role("link", name="Hilfe zum Raumzugang").click()
    page.wait_for_function("() => document.getElementById('qr-zugang').open")
    assert page.get_by_text("Scanne einen aktuellen Raum-QR-Code", exact=False).is_visible()


def test_logbook_search_and_paging_in_browser(page, live_url):
    add_entries(25, condition="Problem/Defekt", remark="Bohrer klemmt")
    add_entries(1, "sauna", remark="Sauna gereinigt")
    unlock(page, live_url)
    page.goto(live_url + "/logbuch")
    page.get_by_role("searchbox", name="Suche").fill("Bohrer")
    page.get_by_role("combobox", name="Zustand", exact=True).select_option("Problem/Defekt")
    page.get_by_role("button", name="Filtern", exact=True).click()
    page.get_by_role("link", name="Werkstatt", exact=True).click()
    page.get_by_role("link", name="Ältere", exact=True).click()
    page.wait_for_url("**/*seite=2")
    assert page.get_by_role("searchbox", name="Suche").input_value() == "Bohrer"
    assert (
        page.get_by_role("combobox", name="Zustand", exact=True).input_value() == "Problem/Defekt"
    )
    assert page.locator(".entry-table tbody tr").count() == 5
    page.get_by_role("link", name="Filter zurücksetzen", exact=True).click()
    page.wait_for_url(live_url + "/logbuch")


def test_latest_status_and_retry(page, live_url):
    add_entries(1)
    unlock(page, live_url)
    page.route(
        "**/rooms/latest-status", lambda route: route.fulfill(status=503, body="unavailable")
    )
    page.goto(live_url)
    retry = page.get_by_role("button", name="Erneut versuchen", exact=True)
    retry.wait_for()
    page.unroute("**/rooms/latest-status")
    retry.click()
    page.locator('[data-room-status="werkstatt"] time').wait_for()
    assert (
        page.locator('[data-room-status="werkstatt"]')
        .inner_text()
        .startswith("Letzte Meldung\nSauber")
    )
    assert "Noch keine Zustandsmeldung" in page.locator('[data-room-status="sauna"]').inner_text()


def test_upload_limits_block_submission_and_recover(page, live_url):
    page.goto(live_url + "/r/werkstatt")
    test_browser.fill_usage(page)
    field = page.locator(".file-input")
    files = [
        {"name": f"{index}.png", "mimeType": "image/png", "buffer": b"bad-image"}
        for index in range(6)
    ]
    field.set_input_files(files)
    assert "höchstens 5 Bilder" in page.locator("[data-file-error]").inner_text()
    page.get_by_role("button", name="Nutzung speichern", exact=True).click()
    assert page.url.endswith("/r/werkstatt")
    page.get_by_role("button", name="Entfernen", exact=True).last.click()
    assert field.evaluate("el => el.validity.valid")
    field.set_input_files(
        {"name": "gross.png", "mimeType": "image/png", "buffer": b"x" * (5 * 1024 * 1024 + 1)}
    )
    assert "gross.png ist zu groß" in page.locator("[data-file-error]").inner_text()
    page.get_by_role("button", name="Entfernen", exact=True).click()
    assert field.evaluate("el => el.validity.valid")


def test_submit_lock_and_restoration(page, live_url):
    page.goto(live_url + "/r/werkstatt")
    test_browser.fill_usage(page)
    page.evaluate("""() => {
        const form = document.querySelector('form');
        window.acceptedSubmits = 0;
        window.blockTestNavigation = (event) => {
            if (!event.defaultPrevented) window.acceptedSubmits++;
            event.preventDefault();
        };
        form.addEventListener('submit', window.blockTestNavigation);
        form.requestSubmit();
        form.requestSubmit();
    }""")
    assert page.get_by_role("button", name="Wird gespeichert …", exact=True).is_disabled()
    assert page.evaluate("window.acceptedSubmits") == 1
    page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))")
    assert page.get_by_role("button", name="Nutzung speichern", exact=True).is_enabled()
    page.evaluate(
        "document.querySelector('form').removeEventListener('submit', window.blockTestNavigation)"
    )
    page.get_by_role("button", name="Nutzung speichern", exact=True).click()
    page.wait_for_url("**/thanks?**")


@pytest.mark.parametrize("width", [390, 650, 768, 1280])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_responsive_resident_views(page, live_url, width, theme, tmp_path):
    add_entries(1)
    page.set_viewport_size({"width": width, "height": 900})
    unlock(page, live_url)
    page.evaluate("localStorage.setItem('theme', '" + theme + "')")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    for path in ("/", "/r/werkstatt", "/hilfe", "/logbuch", "/thanks?raum=werkstatt"):
        page.goto(live_url + path)
        page.wait_for_function(
            '() => !document.querySelector(\'[data-room-status][aria-busy="true"], [data-room-bookings][aria-busy="true"]\')'
        )
        assert page.locator("html").get_attribute("data-theme") == theme
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        if path in ("/", "/r/werkstatt"):
            label = "rooms" if path == "/" else "form"
            page.screenshot(
                path=str(tmp_path / f"{label}-{width}-{theme}.png"),
                full_page=True,
                animations="disabled",
            )
        if path == "/":
            columns = page.locator(".room-grid").evaluate(
                "el => getComputedStyle(el).gridTemplateColumns.split(' ').length"
            )
            assert columns == (1 if width < 640 else 2 if width < 960 else 3)
        if path == "/r/werkstatt":
            assert page.locator(".content-narrow").first.bounding_box()["width"] <= 760
            assert page.locator("footer [data-remember-enabled]").is_visible()
            assert page.locator("form .form-note").inner_text() == (
                "Mit dem Speichern akzeptierst du die Datenschutzhinweise."
            )
            assert page.locator("form .form-note").evaluate(
                "el => el.nextElementSibling.matches('button[type=submit]')"
            )
        else:
            assert page.locator("footer .room-footer").count() == 0
    assert errors == []


@pytest.mark.parametrize("width", [390, 650, 768, 1280])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_admin_filters_fit_and_remain_usable(page, live_url, width, theme, tmp_path):
    page.set_viewport_size({"width": width, "height": 900})
    page.emulate_media(reduced_motion="reduce")
    page.add_init_script(f"localStorage.setItem('theme', '{theme}')")
    page.goto(live_url + "/admin")
    page.get_by_label("Suche", exact=True).fill("Eine lange Suche nach einer Nutzung")
    page.get_by_role("combobox", name="Raum", exact=True).select_option("werkstatt")
    page.get_by_role("combobox", name="Zustand", exact=True).select_option("Problem/Defekt")
    page.screenshot(
        path=str(tmp_path / f"admin-filters-{width}-{theme}.png"),
        full_page=True,
        animations="disabled",
    )
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert page.locator(".admin-filter-form").evaluate("el => el.scrollWidth <= el.clientWidth")
    for control in page.locator(".admin-filter-form").locator("input, select, button, a").all():
        box = control.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width
        assert box["height"] >= 44
    page.get_by_role("button", name="Filtern", exact=True).click()
    assert page.get_by_label("Suche", exact=True).input_value() == (
        "Eine lange Suche nach einer Nutzung"
    )
    assert page.get_by_role("combobox", name="Raum", exact=True).input_value() == "werkstatt"
    assert (
        page.get_by_role("combobox", name="Zustand", exact=True).input_value() == "Problem/Defekt"
    )
    page.get_by_role("link", name="Zurücksetzen", exact=True).click()
    assert page.get_by_label("Suche", exact=True).input_value() == ""
    assert page.get_by_role("combobox", name="Raum", exact=True).input_value() == ""
    assert page.get_by_role("combobox", name="Zustand", exact=True).input_value() == ""


def test_saved_page_navigation_and_checklist(page, live_url):
    page.goto(live_url + "/r/werkstatt")
    test_browser.fill_usage(page)
    page.get_by_role("button", name="Nutzung speichern", exact=True).click()
    page.wait_for_url("**/thanks?raum=werkstatt")
    assert page.get_by_role("heading", name="Eintrag gespeichert", exact=True).is_visible()
    primary = page.get_by_role("link", name="Zur Raumübersicht", exact=True)
    assert primary.get_attribute("href") == "/" and "button" in primary.get_attribute("class")
    another = page.get_by_role("link", name="Noch einen Eintrag für Werkstatt anlegen")
    assert another.get_attribute("href") == "/r/werkstatt"
    assert "button" not in (another.get_attribute("class") or "")
    items = page.locator("[data-checklist-input]")
    items.first.focus()
    page.keyboard.press("Space")
    assert page.locator("[data-checklist-progress]").inner_text() == f"1 / {items.count()} erledigt"
    for item in items.all():
        if not item.is_checked():
            item.focus()
            page.keyboard.press("Space")
    assert page.locator("[data-checklist-success]").is_visible()
    assert page.locator("[data-checklist-progress]").inner_text() == (
        f"{items.count()} / {items.count()} erledigt"
    )
