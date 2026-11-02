import base64
import hashlib
import hmac
import io
import re
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from PIL import Image

from app import capabilities, db, middleware
from app.main import app
from app.routes import public
from app.services import pdf
from tests.conftest import VALID, admin_auth


@pytest.fixture
def reader_client(paths):
    with TestClient(
        app, base_url="https://testserver", headers={"Origin": "https://testserver"}
    ) as client:
        yield client


@pytest.fixture
def clock(monkeypatch):
    value = {"now": 2_000_000_000}
    monkeypatch.setattr(capabilities, "utc_timestamp", lambda: value["now"])
    return value


def room(slug="sauna"):
    with db.db_connect() as conn:
        return db.load_room_by_slug(conn, slug)


def token(slug="sauna"):
    current = room(slug)
    return capabilities.derive_room_token(current["id"], current["qr_key_version"])


def grant(client, slug="sauna", value=None):
    return client.post(f"/r/{slug}/access", json={"token": value or token(slug)})


def rotation(client):
    response = client.get("/admin/raumzugaenge", auth=admin_auth(client))
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', response.text)[1]
    return client.post(
        "/admin/reader-access/rotate",
        auth=admin_auth(client),
        data={"csrf_token": csrf},
        follow_redirects=False,
    )


def stored_session(client):
    raw = client.cookies.get(capabilities.READER_COOKIE)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    with db.db_connect() as conn:
        return dict(
            conn.execute("SELECT * FROM reader_sessions WHERE id_hash=?", (digest,)).fetchone()
        )


def assert_cookie_expiry(response, now, expires_at):
    cookies = SimpleCookie()
    for value in response.headers.get_list("set-cookie"):
        cookies.load(value)
    cookie = cookies[capabilities.READER_COOKIE]
    assert int(cookie["max-age"]) == expires_at - now
    assert int(parsedate_to_datetime(cookie["expires"]).timestamp()) == expires_at
    assert cookie["httponly"] and cookie["samesite"] == "lax" and not cookie["domain"]


def test_workshop_scan_grants_all_logbooks_and_all_pdfs(reader_client):
    client = reader_client
    for slug, name in [("werkstatt", "WORKSHOP-ENTRY"), ("dachterrasse", "TERRACE-ENTRY")]:
        assert (
            client.post(
                f"/r/{slug}/submit", data={**VALID, "person_name": name}, follow_redirects=False
            ).status_code
            == 303
        )
    assert grant(client, "werkstatt").status_code == 204
    for slug, name in [("werkstatt", "WORKSHOP-ENTRY"), ("dachterrasse", "TERRACE-ENTRY")]:
        response = client.get(f"/logbuch?raum={slug}")
        assert response.status_code == 200 and name in response.text
    assert "TERRACE-ENTRY" in client.get("/logbuch").text
    assert client.get("/r/sauna/qr.pdf").status_code == 200
    assert client.get("/r/ruheraum/qr.pdf").status_code == 200


@pytest.mark.parametrize("path", ["/logbuch", "/r/sauna/qr.pdf", "/uploads/unknown.png"])
def test_missing_reader_never_prompts_for_admin(reader_client, path):
    response = reader_client.get(path)
    assert response.status_code == 403
    assert "www-authenticate" not in response.headers
    assert "no-store" in response.headers["cache-control"]


def test_reader_has_no_admin_rights(reader_client):
    grant(reader_client, "werkstatt")
    assert reader_client.get("/admin").status_code == 401
    assert reader_client.get("/admin/nachrichten").status_code == 401
    assert reader_client.post("/admin/reader-access/rotate").status_code == 401
    assert reader_client.post("/admin/session/1/delete").status_code == 401


def test_admin_can_print_all_pdfs_without_reader_session(reader_client):
    assert reader_client.get("/r/sauna/qr.pdf", auth=admin_auth(reader_client)).status_code == 200
    assert (
        reader_client.get(
            f"/admin/rooms/{room()['id']}/qr.pdf", auth=admin_auth(reader_client)
        ).status_code
        == 200
    )
    assert capabilities.READER_COOKIE not in reader_client.cookies


def test_tokens_stay_room_specific_and_reproducible(reader_client, monkeypatch):
    urls = []
    original = pdf.qr_matrix

    def capture(value):
        urls.append(value)
        return original(value)

    monkeypatch.setattr(pdf, "qr_matrix", capture)
    grant(reader_client, "werkstatt")
    for _ in range(2):
        assert reader_client.get("/r/sauna/qr.pdf").status_code == 200
    assert urls[0] == urls[1]
    assert parse_qs(urlsplit(urls[0]).fragment) == {"access": [token()]}
    assert "access" not in urlsplit(urls[0]).query
    assert token() != token("werkstatt")
    assert capabilities.master_key().hex() not in urls[0]


def test_derivation_has_domain_separation(reader_client):
    current = room()
    expected = hmac.digest(
        capabilities.master_key(),
        b"zelter5/room-access/v1\0" + f"{current['id']}:1".encode(),
        "sha256",
    )
    assert token() == base64.urlsafe_b64encode(expected).decode().rstrip("=")
    assert token() != capabilities.current_master_id(capabilities.master_key())
    assert token() != capabilities.derive_room_token(current["id"], 2)


def test_default_lifetime_is_365_days_with_persistent_secure_cookie(reader_client, clock):
    assert capabilities.READER_SESSION_SECONDS == 365 * 86400
    response = grant(reader_client)
    expires_at = clock["now"] + 365 * 86400
    assert stored_session(reader_client)["expires_at"] == expires_at
    assert_cookie_expiry(response, clock["now"], expires_at)
    assert "Secure" in response.headers["set-cookie"]


def test_every_successful_access_slides_db_and_cookie_without_90_day_threshold(
    reader_client, clock
):
    grant(reader_client)
    for advance in [1, 60, 86400, 91 * 86400]:
        previous = stored_session(reader_client)["expires_at"]
        clock["now"] += advance
        response = reader_client.get("/logbuch")
        expires_at = clock["now"] + 365 * 86400
        assert response.status_code == 200
        assert stored_session(reader_client)["expires_at"] == expires_at > previous
        assert_cookie_expiry(response, clock["now"], expires_at)


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/r/sauna",
        "/hilfe",
        "/datenschutz",
        "/static/theme.js",
        "/missing",
        "/r/missing/qr.pdf",
        "/uploads/missing.png",
        "/admin",
    ],
)
def test_public_and_failed_requests_do_not_refresh(reader_client, clock, path):
    grant(reader_client)
    previous = stored_session(reader_client)["expires_at"]
    clock["now"] += 100
    response = reader_client.get(path)
    assert stored_session(reader_client)["expires_at"] == previous
    assert "set-cookie" not in response.headers


def test_failed_public_form_and_failed_copy_do_not_refresh(reader_client, clock):
    grant(reader_client)
    previous = stored_session(reader_client)["expires_at"]
    clock["now"] += 100
    response = reader_client.post("/r/sauna/submit", data={**VALID, "person_name": " "})
    assert response.status_code == 400 and "set-cookie" not in response.headers
    response = reader_client.post(
        "/r/sauna/access-link", headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403 and "set-cookie" not in response.headers
    assert stored_session(reader_client)["expires_at"] == previous


def test_configurable_lifetime_and_https_secure_only(reader_client, clock, monkeypatch):
    monkeypatch.setattr(capabilities, "READER_SESSION_SECONDS", 1234)
    response = grant(reader_client)
    assert_cookie_expiry(response, clock["now"], clock["now"] + 1234)
    with TestClient(
        app, base_url="http://localhost", headers={"Origin": "http://localhost"}
    ) as local:
        response = grant(local)
        assert "Secure" not in response.headers["set-cookie"]
        assert "HttpOnly" in response.headers["set-cookie"]


def test_rescan_reuses_valid_session_and_slides(reader_client, clock):
    grant(reader_client, "werkstatt")
    raw = reader_client.cookies.get(capabilities.READER_COOKIE)
    clock["now"] += 200
    response = grant(reader_client, "sauna")
    assert response.status_code == 204
    assert reader_client.cookies.get(capabilities.READER_COOKIE) == raw
    assert_cookie_expiry(response, clock["now"], clock["now"] + 365 * 86400)
    with db.db_connect() as conn:
        assert conn.execute("SELECT count(*) FROM reader_sessions").fetchone()[0] == 1
        assert not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='reader_room_grants'"
        ).fetchone()


def test_restart_preserves_session_and_key_versions(reader_client, clock):
    grant(reader_client)
    raw = reader_client.cookies.get(capabilities.READER_COOKIE)
    original_token = token()
    db.init_db()
    db.init_db()
    with TestClient(app, base_url="https://testserver") as restarted:
        restarted.cookies.set(capabilities.READER_COOKIE, raw)
        assert restarted.get("/r/dachterrasse/qr.pdf").status_code == 200
    assert token() == original_token


def test_expired_session_is_never_renewed_or_reactivated(reader_client, clock):
    grant(reader_client)
    original = stored_session(reader_client)
    raw = reader_client.cookies.get(capabilities.READER_COOKIE)
    clock["now"] = original["expires_at"]
    response = reader_client.get("/logbuch")
    assert response.status_code == 403 and "set-cookie" not in response.headers
    assert stored_session(reader_client)["expires_at"] == original["expires_at"]
    assert grant(reader_client).status_code == 204
    assert reader_client.cookies.get(capabilities.READER_COOKIE) != raw


def test_global_rotation_revokes_every_session_and_every_known_room_token(reader_client, clock):
    client = reader_client
    old_tokens = {slug: token(slug) for slug in ["werkstatt", "sauna", "dachterrasse"]}
    grant(client, "werkstatt")
    original = stored_session(client)
    assert rotation(client).status_code == 303
    assert client.get("/r/sauna/qr.pdf").status_code == 403
    assert stored_session(client)["expires_at"] == original["expires_at"]
    for slug, value in old_tokens.items():
        assert token(slug) != value
        assert grant(client, slug, value).status_code == 403
    assert grant(client, "sauna").status_code == 204
    assert stored_session(client)["id_hash"] != original["id_hash"]
    assert client.get("/r/dachterrasse/qr.pdf").status_code == 200
    db.init_db()
    assert grant(client, "werkstatt", old_tokens["werkstatt"]).status_code == 403


def test_rotation_requires_admin_and_csrf(reader_client):
    grant(reader_client)
    path = "/admin/reader-access/rotate"
    assert reader_client.post(path).status_code == 401
    assert reader_client.post(path, auth=admin_auth(reader_client)).status_code == 403
    assert (
        reader_client.post(
            f"/admin/rooms/{room()['id']}/rotate-key",
            auth=admin_auth(reader_client),
            data={"csrf_token": "old"},
        ).status_code
        == 404
    )
    assert room()["qr_key_version"] == 1


def test_session_fixation_and_legacy_sessions_are_not_accepted(reader_client):
    chosen = "a" * 43
    reader_client.cookies.set(capabilities.READER_COOKIE, chosen)
    response = grant(reader_client)
    assert response.status_code == 204 and chosen not in response.headers["set-cookie"]
    with db.db_connect() as conn:
        conn.execute("UPDATE reader_sessions SET access_version=0")
    assert reader_client.get("/logbuch").status_code == 403


def test_no_room_grant_table_is_needed_at_runtime(reader_client):
    with db.db_connect() as conn:
        assert not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='reader_room_grants'"
        ).fetchone()
    assert grant(reader_client, "werkstatt").status_code == 204
    assert reader_client.get("/r/sauna/qr.pdf").status_code == 200


def test_cross_room_images_and_soft_delete(reader_client, clock):
    output = io.BytesIO()
    with Image.new("RGB", (12, 12), "red") as image:
        image.save(output, "PNG")
    reader_client.post(
        "/r/dachterrasse/submit", data=VALID, files={"images": ("test.png", output.getvalue())}
    )
    grant(reader_client, "werkstatt")
    with db.db_connect() as conn:
        filename = conn.execute("SELECT filename FROM usage_images").fetchone()[0]
    previous = stored_session(reader_client)["expires_at"]
    clock["now"] += 1
    response = reader_client.get("/uploads/" + filename)
    assert response.status_code == 200
    assert stored_session(reader_client)["expires_at"] == previous + 1
    with db.db_connect() as conn:
        db.soft_delete_session(conn, 1)
    clock["now"] += 1
    assert reader_client.get("/uploads/" + filename).status_code == 404
    assert stored_session(reader_client)["expires_at"] == previous + 1


def test_copy_link_is_explicit_authorized_and_global(reader_client, clock):
    path = "/r/dachterrasse/access-link"
    response = reader_client.post(path)
    assert response.status_code == 403 and "www-authenticate" not in response.headers
    grant(reader_client, "werkstatt")
    assert token("dachterrasse") not in reader_client.get("/r/dachterrasse").text
    clock["now"] += 123
    response = reader_client.post(path)
    assert response.status_code == 200 and "no-store" in response.headers["cache-control"]
    link = urlsplit(response.json()["url"])
    assert link.path == "/r/dachterrasse" and parse_qs(link.fragment)["access"] == [
        token("dachterrasse")
    ]
    assert_cookie_expiry(response, clock["now"], clock["now"] + 365 * 86400)
    with TestClient(
        app, base_url="https://testserver", headers={"Origin": "https://testserver"}
    ) as new_browser:
        assert (
            grant(new_browser, "dachterrasse", parse_qs(link.fragment)["access"][0]).status_code
            == 204
        )
        assert new_browser.get("/r/sauna/qr.pdf").status_code == 200


def test_racing_revocation_suppresses_private_body_and_cookie(reader_client, monkeypatch):
    grant(reader_client)

    def rotate_before_headers(current):
        with db.db_connect() as conn:
            capabilities.rotate_all_reader_access(conn)
        return HTMLResponse("PRIVATE-CONTENT")

    monkeypatch.setattr(public, "room_qr_pdf_response", rotate_before_headers)
    response = reader_client.get("/r/sauna/qr.pdf")
    assert response.status_code == 403
    assert "PRIVATE-CONTENT" not in response.text and "set-cookie" not in response.headers


def test_failed_renewal_fails_closed(reader_client, monkeypatch):
    import sqlite3

    grant(reader_client)

    def fail(*args):
        raise sqlite3.OperationalError("private SQL")

    monkeypatch.setattr(middleware, "renew_reader_session", fail)
    response = reader_client.get("/logbuch")
    assert response.status_code == 503 and "set-cookie" not in response.headers
    assert "private SQL" not in response.text


def test_public_forms_work_without_key_or_reader(reader_client, monkeypatch):
    monkeypatch.delenv("QR_MASTER_KEY")
    assert reader_client.get("/r/sauna").status_code == 200
    assert (
        reader_client.post("/r/sauna/submit", data=VALID, follow_redirects=False).status_code == 303
    )
    assert (
        reader_client.post("/hilfe", data={"note": "public"}, follow_redirects=False).status_code
        == 303
    )
    assert reader_client.get("/r/sauna/qr.pdf", auth=admin_auth(reader_client)).status_code == 503


def test_master_change_revokes_reader_and_old_qr(reader_client, monkeypatch):
    previous = token()
    grant(reader_client)
    monkeypatch.setenv("QR_MASTER_KEY", "23" * 32)
    assert reader_client.get("/r/sauna/qr.pdf").status_code == 403
    assert grant(reader_client, value=previous).status_code == 403
    assert grant(reader_client).status_code == 204


def test_missing_base_has_no_host_fallback(reader_client, monkeypatch):
    monkeypatch.delenv("PUBLIC_BASE_URL")
    assert reader_client.get("/r/sauna/qr.pdf", auth=admin_auth(reader_client)).status_code == 503


@pytest.mark.parametrize(
    "origin,site",
    [
        ("https://evil.example", None),
        ("null", None),
        ("", None),
        ("https://testserver", "cross-site"),
        ("https://testserver", "same-site"),
    ],
)
def test_token_exchange_rejects_csrf(reader_client, origin, site):
    headers = {"Origin": origin}
    if site:
        headers["Sec-Fetch-Site"] = site
    assert (
        reader_client.post("/r/sauna/access", json={"token": token()}, headers=headers).status_code
        == 403
    )
    assert capabilities.READER_COOKIE not in reader_client.cookies


def test_invalid_token_is_never_echoed(reader_client, caplog):
    secret = "private-invalid-token"
    response = reader_client.post("/r/sauna/access", json={"token": secret})
    assert response.status_code == 403 and secret not in response.text + caplog.text
    assert reader_client.post("/r/sauna/access", data={"token": secret}).status_code == 415


def test_form_and_overview_offer_all_qr_actions_after_one_scan(reader_client):
    assert "room-card-qr" not in reader_client.get("/").text
    grant(reader_client, "werkstatt")
    for slug in ["sauna", "dachterrasse"]:
        content = reader_client.get(f"/r/{slug}").text
        assert "QR-PDF herunterladen" in content and "Zugangslink kopieren" in content
        assert token(slug) not in content
    assert 'href="/r/sauna/qr.pdf"' in reader_client.get("/").text


def test_successful_public_submissions_do_not_renew(reader_client, clock):
    grant(reader_client)
    previous = stored_session(reader_client)["expires_at"]
    clock["now"] += 500
    for path, data in [("/r/sauna/submit", VALID), ("/hilfe", {"note": "public"})]:
        response = reader_client.post(path, data=data, follow_redirects=False)
        assert response.status_code == 303 and "set-cookie" not in response.headers
    assert stored_session(reader_client)["expires_at"] == previous


def test_invalid_scan_does_not_renew_an_existing_reader(reader_client, clock):
    grant(reader_client)
    previous = stored_session(reader_client)["expires_at"]
    clock["now"] += 500
    response = grant(reader_client, value="a" * 43)
    assert response.status_code == 403 and "set-cookie" not in response.headers
    assert stored_session(reader_client)["expires_at"] == previous


@pytest.mark.parametrize(
    "path,method", [("/r/sauna/qr.pdf", "get"), ("/r/sauna/access-link", "post")]
)
def test_pdf_and_copy_extend_on_every_success(reader_client, clock, path, method):
    grant(reader_client, "werkstatt")
    clock["now"] += 1
    response = getattr(reader_client, method)(path)
    assert response.status_code == 200
    assert_cookie_expiry(response, clock["now"], clock["now"] + 365 * 86400)
    assert stored_session(reader_client)["expires_at"] == clock["now"] + 365 * 86400


def test_rotation_rolls_back_everything_if_one_update_fails(reader_client):
    grant(reader_client)
    old_token = token()
    with db.db_connect() as conn:
        conn.execute(
            "CREATE TRIGGER fail_rotation BEFORE UPDATE OF qr_key_version ON rooms BEGIN SELECT RAISE(ABORT, 'blocked'); END"
        )
    assert rotation(reader_client).status_code == 503
    with db.db_connect() as conn:
        assert capabilities.global_access_version(conn) == 1
    assert token() == old_token
    assert reader_client.get("/logbuch").status_code == 200


def test_admin_copy_requires_csrf_and_reader_cannot_use_admin_aliases(reader_client):
    grant(reader_client)
    room_id = room()["id"]
    path = f"/admin/rooms/{room_id}/access-link"
    assert reader_client.post(path).status_code == 401
    assert reader_client.post(path, auth=admin_auth(reader_client)).status_code == 403
    response = reader_client.get("/admin/raumzugaenge", auth=admin_auth(reader_client))
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', response.text)[1]
    response = reader_client.post(path, auth=admin_auth(reader_client), data={"csrf_token": csrf})
    assert response.status_code == 200 and "#access=" in response.json()["url"]
    assert reader_client.get(f"/admin/rooms/{room_id}/qr.pdf").status_code == 401
    assert reader_client.get("/admin/uploads/unknown.png").status_code == 401


def test_deactivating_source_room_does_not_revoke_global_session(reader_client):
    grant(reader_client, "werkstatt")
    with db.db_connect() as conn:
        conn.execute("UPDATE rooms SET is_active=0 WHERE slug='werkstatt'")
    assert reader_client.get("/r/sauna/qr.pdf").status_code == 200
    assert reader_client.get("/r/werkstatt/qr.pdf").status_code == 404


def test_invalid_master_never_appears_in_errors(reader_client, monkeypatch):
    secret = "private-invalid-master"
    monkeypatch.setenv("QR_MASTER_KEY", secret)
    response = reader_client.get("/r/sauna/qr.pdf", auth=admin_auth(reader_client))
    assert response.status_code == 503 and secret not in response.text
    with pytest.raises(ValueError) as error:
        capabilities.validate_capability_config()
    assert secret not in str(error.value)


def test_new_rooms_are_readable_without_another_scan(reader_client):
    grant(reader_client, "werkstatt")
    raw = reader_client.cookies.get(capabilities.READER_COOKIE)
    with db.db_connect() as conn:
        conn.execute("INSERT INTO rooms(slug, name) VALUES ('neuer-raum', 'Neuer Raum')")
    assert reader_client.get("/r/neuer-raum/qr.pdf").status_code == 200
    assert reader_client.cookies.get(capabilities.READER_COOKIE) == raw


def test_https_proxy_exchange_uses_public_url_without_trusted_peer(client, monkeypatch):
    protection = app.middleware_stack
    while not isinstance(protection, middleware.RequestProtectionMiddleware):
        protection = protection.app
    monkeypatch.setattr(protection, "trusted_proxies", [])
    headers = {
        "Origin": "https://testserver",
        "Sec-Fetch-Site": "same-origin",
        "X-Forwarded-Proto": "http",
        "X-Forwarded-Host": "evil.example",
        "X-Forwarded-For": "192.0.2.20",
    }
    with TestClient(app, base_url="http://testserver", client=("10.12.0.5", 4321)) as proxy:
        payload = {"token": token("werkstatt")}
        response = proxy.post("/r/werkstatt/access", json=payload, headers=headers)
        assert response.status_code == 204
        cookies = SimpleCookie()
        cookies.load(response.headers["set-cookie"])
        cookie = cookies[capabilities.READER_COOKIE]
        assert cookie["secure"] and cookie["httponly"]
        assert cookie["samesite"] == "lax" and cookie["path"] == "/"
        assert proxy.get("https://testserver/logbuch", headers=headers).status_code == 200
        assert (
            proxy.post(
                "/r/werkstatt/access",
                json=payload,
                headers={**headers, "Origin": "https://evil.example"},
            ).status_code
            == 403
        )
