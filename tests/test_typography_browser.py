"""Schriftrollen, echte Webfonts und Umbrüche mit isolierten Testdaten."""

from urllib.parse import urlsplit

import pytest

from app import db
from tests import test_browser
from tests.conftest import VALID
from tests.test_capabilities import token

browser = test_browser.browser
live_url = test_browser.live_url
page = test_browser.page


def css(locator):
    return locator.evaluate("""el => {
        const s = getComputedStyle(el);
        return {family:s.fontFamily, weight:s.fontWeight, size:parseFloat(s.fontSize),
                leading:parseFloat(s.lineHeight)};
    }""")


def loaded(page):
    page.evaluate("() => document.fonts.ready")


def rendered_fonts(page, selector):
    session = page.context.new_cdp_session(page)
    try:
        session.send("DOM.enable")
        session.send("CSS.enable")
        document = session.send("DOM.getDocument")
        node = session.send(
            "DOM.querySelector", {"nodeId": document["root"]["nodeId"], "selector": selector}
        )
        return session.send("CSS.getPlatformFontsForNode", {"nodeId": node["nodeId"]})["fonts"]
    finally:
        session.detach()


def assert_brand(page, admin=False, enlarged=False):
    brand = page.locator(".site-brand")
    assert brand.inner_text() == ("Zelter5 Verwaltung" if admin else "Zelter5 Raumlog")
    assert brand.get_attribute("href") == ("/admin" if admin else "/")
    assert page.locator(".site-brand-kicker").count() == 0
    style = css(brand.locator("strong"))
    assert style["family"].startswith('"Noto Serif Display"')
    assert style["weight"] == "700"
    assert 24 <= style["size"] <= (64 if enlarged else 32)
    assert style["leading"] == pytest.approx(style["size"] * 1.15, abs=0.05)
    assert any(
        font["isCustomFont"] and font["postScriptName"] == "NotoSerifDisplay-Bold"
        for font in rendered_fonts(page, ".site-brand strong")
    )
    box = brand.bounding_box()
    actions = page.locator(".site-header-actions").bounding_box()
    assert box["x"] + box["width"] <= actions["x"] or box["y"] + box["height"] <= actions["y"]
    assert page.locator(".site-header").evaluate("""el => {
        const edge = innerWidth;
        return [...el.querySelectorAll('*')].every(node => node.getBoundingClientRect().right <= edge);
    }""")
    if not (admin and enlarged):
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [390, 768, 1280])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_typographic_roles_use_real_local_fonts(page, live_url, client, width, theme, tmp_path):
    client.post("/r/werkstatt/submit", data=VALID)
    page.set_viewport_size({"width": width, "height": 900})
    page.emulate_media(reduced_motion="reduce")
    page.add_init_script(f"localStorage.setItem('theme', '{theme}')")
    font_requests = []
    page.on(
        "request",
        lambda request: (
            font_requests.append(request.url) if request.resource_type == "font" else None
        ),
    )
    page.goto(live_url + "/r/werkstatt#access=" + token("werkstatt"))
    page.get_by_role("link", name="QR-PDF herunterladen", exact=True).wait_for()
    for path in [
        "/",
        "/r/werkstatt",
        "/hilfe#geraet",
        "/datenschutz",
        "/logbuch",
        "/thanks?raum=werkstatt",
    ]:
        page.goto(live_url + path)
        loaded(page)
        heading = css(page.locator("h1"))
        assert heading["family"].startswith('"Noto Serif Display"')
        assert heading["weight"] == "500" and 32 <= heading["size"] <= 40
        assert heading["leading"] == pytest.approx(heading["size"] * 1.15, abs=0.05)
        assert_brand(page)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        if path == "/":
            title = css(page.locator(".room-card h2").first)
            assert title["family"].startswith('"Noto Serif Display"') and title["size"] == 24
            actual = rendered_fonts(page, "h1")
            assert any(
                font["isCustomFont"] and font["postScriptName"] == "NotoSerifDisplay-Medium"
                for font in actual
            ), actual
            assert any(
                font["isCustomFont"] and "Google Sans Flex" in font["familyName"]
                for font in rendered_fonts(page, ".room-card p")
            )
        if path == "/r/werkstatt":
            assert css(page.get_by_label("Name", exact=True))["weight"] == "400"
            assert css(page.locator("#room-usage-form > label").first)["weight"] == "600"
            assert (
                css(page.get_by_role("button", name="Nutzung speichern", exact=True))["weight"]
                == "700"
            )
            assert css(page.get_by_role("heading", name="Letzte Buchungen", exact=True))[
                "family"
            ].startswith('"Google Sans Flex"')
            title = page.locator(".room-heading h1").bounding_box()
            actions = page.locator(".room-heading-actions").bounding_box()
            assert title["x"] + title["width"] + 7 <= actions["x"]
            columns = page.locator(".house-fields").evaluate(
                "el => getComputedStyle(el).gridTemplateColumns.split(' ').length"
            )
            assert columns == (1 if width < 640 else 2)
        for heading in page.locator("h2:not(.room-card h2)").all():
            assert css(heading)["family"].startswith('"Google Sans Flex"')
        page.screenshot(
            path=str(
                tmp_path
                / f"type-{path.split('?')[0].replace('/', '-') or 'rooms'}-{width}-{theme}.png"
            ),
            full_page=True,
            animations="disabled",
        )
    test_browser.login_admin(page, live_url, "/admin/raumzugaenge")
    loaded(page)
    assert css(page.locator("h1"))["family"].startswith('"Noto Serif Display"')
    assert css(page.locator(".room-card h2").first)["family"].startswith('"Noto Serif Display"')
    assert css(page.get_by_role("button", name="Abmelden", exact=True))["family"].startswith(
        '"Google Sans Flex"'
    )
    assert font_requests and all(
        urlsplit(url).netloc == urlsplit(live_url).netloc for url in font_requests
    )
    assert any("noto-serif-display-500-latin.woff2" in url for url in font_requests)
    assert any("noto-serif-display-700-latin.woff2" in url for url in font_requests)


@pytest.mark.parametrize("width", [390, 768, 1280])
def test_long_room_names_extended_latin_and_enlarged_text(page, live_url, width, tmp_path):
    name = "Werkstatt für Holz, Metall & Reparaturen – ÄÖÜ äöü ß Ā Ł"
    with db.db_connect() as conn:
        conn.execute("UPDATE rooms SET name=? WHERE slug='werkstatt'", (name,))
    page.set_viewport_size({"width": width, "height": 900})
    page.emulate_media(reduced_motion="reduce")
    page.goto(live_url + "/r/werkstatt#access=" + token("werkstatt"))
    page.get_by_role("link", name="QR-PDF herunterladen", exact=True).wait_for()
    loaded(page)
    assert page.get_by_role("heading", name=name, exact=True).inner_text() == name
    actual = rendered_fonts(page, "h1")
    assert actual and all(
        font["isCustomFont"] and font["postScriptName"] == "NotoSerifDisplay-Medium"
        for font in actual
    )
    for path in ["/", "/r/werkstatt", "/hilfe#geraet", "/datenschutz"]:
        page.goto(live_url + path)
        loaded(page)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.evaluate("document.documentElement.style.fontSize = '200%'")
        overflow = page.evaluate("""() => {
            const nodes = [...document.querySelectorAll('main *')].filter(el => el.clientWidth && el.scrollWidth > el.clientWidth + 1).slice(0,12).map(el => ({tag:el.tagName, class:el.className, id:el.id, client:el.clientWidth, scroll:el.scrollWidth}));
            const texts=[]; const walker=document.createTreeWalker(document.querySelector('main'),NodeFilter.SHOW_TEXT);
            while(walker.nextNode()) {const node=walker.currentNode; if(!node.textContent.trim()) continue; const r=document.createRange(); r.selectNodeContents(node); const box=r.getBoundingClientRect(); if(box.width && box.right>innerWidth) texts.push({parent:node.parentElement.className,text:node.textContent.trim().slice(0,80),right:box.right});}
            return {width:innerWidth,scroll:document.documentElement.scrollWidth,nodes,texts};
        }""")
        if not page.evaluate("document.documentElement.scrollWidth <= innerWidth"):
            page.screenshot(path=str(tmp_path / "overflow.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), overflow
        if path == "/r/werkstatt":
            heading = page.locator("h1").bounding_box()
            actions = page.locator(".room-heading-actions").bounding_box()
            assert heading["x"] + heading["width"] + 7 <= actions["x"]
            page.get_by_role(
                "button", name="Nutzung speichern", exact=True
            ).scroll_into_view_if_needed()
            assert page.get_by_role("button", name="Nutzung speichern", exact=True).is_visible()


def test_font_failure_keeps_forms_and_actions_usable(page, live_url):
    page.set_viewport_size({"width": 390, "height": 900})
    page.route("**/static/fonts/**", lambda route: route.abort())
    page.goto(live_url + "/r/werkstatt")
    loaded(page)
    assert page.get_by_role("heading", name="Werkstatt", exact=True).is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    actual = rendered_fonts(page, "h1")
    assert actual and all(not font["isCustomFont"] for font in actual)
    test_browser.fill_usage(page)
    page.get_by_role("button", name="Nutzung speichern", exact=True).click()
    page.wait_for_url("**/thanks?**")
    assert page.get_by_role("heading", name="Eintrag gespeichert", exact=True).is_visible()


@pytest.mark.parametrize("width", [390, 768, 1280])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_header_login_admin_and_enlarged_text(page, live_url, width, theme, tmp_path):
    page.set_viewport_size({"width": width, "height": 900})
    page.add_init_script(f"localStorage.setItem('theme', '{theme}')")
    page.goto(live_url + "/admin/anmelden")
    loaded(page)
    assert_brand(page, admin=True)
    page.locator(".site-brand").evaluate("el => el.focus()")
    assert page.locator(".site-brand").evaluate("el => el === document.activeElement")
    page.screenshot(path=str(tmp_path / f"login-{width}-{theme}.png"))
    test_browser.login_admin(page, live_url)
    for path in ["/admin", "/admin/nachrichten", "/admin/raumzugaenge"]:
        page.goto(live_url + path)
        loaded(page)
        assert_brand(page, admin=True)
        page.screenshot(
            path=str(tmp_path / f"header-{path.rsplit('/', 1)[-1]}-{width}-{theme}.png")
        )
        page.evaluate("document.documentElement.style.fontSize = '200%'")
        loaded(page)
        assert_brand(page, admin=True, enlarged=True)
    page.goto(live_url + "/")
    page.evaluate("document.documentElement.style.fontSize = '200%'")
    loaded(page)
    assert_brand(page, enlarged=True)
