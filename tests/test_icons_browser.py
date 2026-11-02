"""Lokale Icons und ihre Aktionen im Browser, ausschließlich mit Testdaten."""

import io

import pytest
from PIL import Image

from tests import test_browser
from tests.conftest import VALID
from tests.test_capabilities import token

browser = test_browser.browser
live_url = test_browser.live_url
page = test_browser.page


def unlock(page, live_url):
    page.goto(live_url + "/r/werkstatt#access=" + token("werkstatt"))
    page.get_by_role("link", name="QR-PDF herunterladen", exact=True).wait_for()


def wait_for_icons(page):
    page.wait_for_function("""() => [...document.querySelectorAll('.icon')]
        .filter(icon => icon.getClientRects().length)
        .every(icon => icon.getBBox().width > 0)""")


def check_targets(page):
    for target in page.locator(".icon-button:visible").all():
        box = target.bounding_box()
        assert box["width"] >= 44 and box["height"] >= 44
        assert box["x"] >= 0 and box["x"] + box["width"] <= page.viewport_size["width"]
        assert target.get_attribute("aria-label")


@pytest.mark.parametrize("width", [390, 768, 1280])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_icon_actions_and_responsive_viewer(page, live_url, client, width, theme, tmp_path):
    output = io.BytesIO()
    Image.new("RGB", (64, 48), "#507060").save(output, "PNG")
    client.post(
        "/r/werkstatt/submit",
        data=VALID,
        files=[
            ("images", ("one.png", output.getvalue())),
            ("images", ("two.png", output.getvalue())),
        ],
    )
    requests, errors = [], []
    page.on("request", lambda request: requests.append(request.url))
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.set_viewport_size({"width": width, "height": 900})
    page.emulate_media(reduced_motion="reduce")
    unlock(page, live_url)
    if theme == "dark":
        page.get_by_role("button", name="Dunkle Ansicht aktivieren", exact=True).click()
    page.goto(live_url)
    theme_name = "Helle Ansicht aktivieren" if theme == "dark" else "Dunkle Ansicht aktivieren"
    theme_icon = "sun" if theme == "dark" else "moon"
    theme_button = page.get_by_role("button", name=theme_name, exact=True)
    assert theme_button.locator(f'[data-icon="{theme_icon}"]').is_visible()
    theme_button.focus()
    assert theme_button.evaluate("el => getComputedStyle(el, '::after').visibility") == "visible"
    assert theme_button.evaluate("el => getComputedStyle(el).outlineStyle") == "solid"
    entry = page.get_by_role("link", name="Verwaltung", exact=True)
    assert entry.get_attribute("href") == "/admin"
    entry.click()
    page.get_by_label("Benutzername", exact=True).wait_for()
    page.get_by_role("link", name="Zur App", exact=True).click()
    page.wait_for_url(live_url + "/")
    wait_for_icons(page)
    check_targets(page)
    page.screenshot(
        path=str(tmp_path / f"icons-rooms-{width}-{theme}.png"),
        full_page=True,
        animations="disabled",
    )
    page.get_by_role("link", name="Werkstatt", exact=True).click()
    page.get_by_role("button", name=theme_name, exact=True).wait_for()
    page.locator("[data-room-bookings] [data-viewer-images]").wait_for()
    page.locator(".file-input").set_input_files(
        {"name": "photo.png", "mimeType": "image/png", "buffer": output.getvalue()}
    )
    assert page.locator("[data-file-title]").inner_text() == "Bild ausgewählt"
    assert page.locator('.file-drop [data-icon="image-plus"]').is_visible()
    wait_for_icons(page)
    check_targets(page)
    page.screenshot(
        path=str(tmp_path / f"icons-form-{width}-{theme}.png"),
        full_page=True,
        animations="disabled",
    )
    trigger = page.get_by_role("button", name="2 Bilder", exact=True)
    assert trigger.locator('[data-icon="images"]').is_visible()
    trigger.click()
    page.get_by_role("dialog", name="Bilder ansehen", exact=True).wait_for()
    wait_for_icons(page)
    page.wait_for_function("""() => document.querySelector('.image-viewer-panel')
        .getAnimations().every(animation => animation.playState === 'finished')""")
    # Der Hintergrund ist inert; nur die Viewer-Buttons sind hier relevant.
    for control in page.locator("[data-image-viewer] .icon-button").all():
        box = control.bounding_box()
        assert box["width"] == 44 and box["height"] == 44
        assert box["x"] >= 0 and box["x"] + box["width"] <= width
    page.get_by_role("button", name="Nächstes Bild", exact=True).click()
    assert page.locator("[data-viewer-count]").inner_text() == "2 von 2"
    page.get_by_role("button", name="Vorheriges Bild", exact=True).click()
    assert page.locator("[data-viewer-count]").inner_text() == "1 von 2"
    page.screenshot(
        path=str(tmp_path / f"icons-viewer-{width}-{theme}.png"),
        full_page=True,
        animations="disabled",
    )
    page.keyboard.press("Escape")
    assert trigger.evaluate("el => document.activeElement === el")
    assert not errors
    assert all(url.startswith(live_url) for url in requests if url.startswith("http"))


def test_copy_feedback_only_on_success_and_resets_after_two_seconds(page, live_url):
    page.clock.install()
    unlock(page, live_url)
    page.evaluate("""() => Object.defineProperty(navigator, 'clipboard', {
        value: {writeText: async () => { if (window.failClipboard) throw new Error('blocked'); }}
    })""")
    button = page.get_by_role("button", name="Zugangslink kopieren", exact=True)
    button.click()
    page.locator("[data-copy-access-link].is-copied").wait_for()
    assert button.locator("[data-copied-icon]").is_visible()
    assert button.locator("[data-copy-icon]").is_hidden()
    assert page.locator("[data-access-link-status]").inner_text() == "Zugangslink kopiert."
    page.clock.fast_forward(2100)
    assert button.locator("[data-copy-icon]").is_visible()
    assert "is-copied" not in button.get_attribute("class")
    page.evaluate("window.failClipboard = true")
    button.click()
    page.get_by_role("textbox", name="Zugangslink zum Kopieren", exact=True).wait_for()
    assert button.locator("[data-copied-icon]").is_hidden()
    assert button.locator("[data-copy-icon]").is_visible()


def test_theme_labels_with_blocked_storage_and_static_icon_delivery(page, live_url):
    page.add_init_script(
        "Object.defineProperty(window, 'localStorage', {get() { throw new Error('blocked'); }});"
    )
    page.goto(live_url)
    page.get_by_role("button", name="Dunkle Ansicht aktivieren", exact=True).click()
    button = page.get_by_role("button", name="Helle Ansicht aktivieren", exact=True)
    assert button.locator('[data-icon="sun"]').is_visible()
    button.click()
    assert page.get_by_role("button", name="Dunkle Ansicht aktivieren", exact=True).is_visible()
    response = page.request.get(live_url + "/static/icons/lucide/sprite.svg")
    assert response.status == 200 and response.headers["content-type"].startswith("image/svg+xml")


@pytest.mark.parametrize("width", [390, 768, 1280])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_navigation_and_room_symbols_wrap_without_changing_links(
    page, live_url, width, theme, tmp_path
):
    page.set_viewport_size({"width": width, "height": 900})
    page.emulate_media(reduced_motion="reduce")
    page.add_init_script(f"localStorage.setItem('theme', '{theme}')")
    for path in ["/", "/r/werkstatt", "/hilfe"]:
        page.goto(live_url + path)
        wait_for_icons(page)
        nav = page.get_by_role("navigation", name="Hauptnavigation", exact=True)
        assert nav.locator("svg").count() == 3
        for name, symbol in [
            ("Alle Räume" if path.startswith("/r/") else "Räume", "door-open"),
            ("Logbuch", "notebook-pen"),
            ("Hilfe & Infos", "circle-question-mark"),
        ]:
            link = nav.get_by_role("link", name=name, exact=True)
            assert link.locator("svg").get_attribute("data-icon") == symbol
            assert link.locator("svg").get_attribute("aria-hidden") == "true"
            link.focus()
            assert link.evaluate("el => el === document.activeElement")
        if path == "/":
            for slug, symbol in [
                ("werkstatt", "wrench"),
                ("dachterrasse", "fence"),
                ("sommerkueche", "cooking-pot"),
                ("sauna", "heater"),
                ("ruheraum", "armchair"),
            ]:
                assert (
                    page.locator(f'.room-card-link[href="/r/{slug}"] svg').get_attribute(
                        "data-icon"
                    )
                    == symbol
                )
            page.screenshot(path=str(tmp_path / f"navigation-rooms-{width}-{theme}.png"))
        for scale in ["100%", "200%"]:
            page.evaluate("scale => document.documentElement.style.fontSize = scale", scale)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert nav.evaluate("""el => [...el.querySelectorAll('a, svg, span')].every(node => {
                const r = node.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth;
            })""")


def test_unknown_room_uses_door_and_long_title_keeps_qr_separate(page, live_url):
    from app import db

    with db.db_connect() as conn:
        conn.execute("UPDATE rooms SET slug='neuer-raum' WHERE slug='ruheraum'")
        conn.execute(
            "UPDATE rooms SET name=? WHERE slug='werkstatt'",
            ("Werkstatt für Holz, Metall und gemeinsame Reparaturen",),
        )
    page.emulate_media(reduced_motion="reduce")
    unlock(page, live_url)
    page.set_viewport_size({"width": 390, "height": 900})
    page.goto(live_url)
    wait_for_icons(page)
    assert (
        page.locator('.room-card-link[href="/r/neuer-raum"] svg').get_attribute("data-icon")
        == "door-open"
    )
    title = page.locator('.room-card-link[href="/r/werkstatt"]')
    title.focus()
    assert title.evaluate("el => el === document.activeElement")
    for scale in ["100%", "200%"]:
        page.evaluate("scale => document.documentElement.style.fontSize = scale", scale)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        icon = title.locator("svg").bounding_box()
        text = title.locator("span").bounding_box()
        qr = page.locator(".room-card-qr").first.bounding_box()
        assert icon["width"] == pytest.approx(22, abs=0.1)
        assert icon["height"] == pytest.approx(22, abs=0.1)
        assert icon["y"] < text["y"] + 35
        assert text["x"] + text["width"] <= qr["x"]
    page.evaluate("document.documentElement.style.fontSize = '100%'")
    with page.expect_download() as download:
        page.locator(".room-card-qr").first.click()
    assert download.value.suggested_filename.endswith(".pdf")
    assert page.url == live_url + "/"
    title.click()
    page.wait_for_url("**/r/werkstatt")
    test_browser.login_admin(page, live_url)
    assert page.get_by_role("navigation", name="Verwaltungsnavigation").locator("svg").count() == 0
