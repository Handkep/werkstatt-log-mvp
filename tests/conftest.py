"""Testumgebung vor JEDEM App-Import isolieren; niemals auf data/app.db zugreifen."""

import atexit
import os
import re
import secrets
import tempfile

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

_BOOTSTRAP = tempfile.TemporaryDirectory(prefix="raumlog-test-import-")
atexit.register(_BOOTSTRAP.cleanup)
os.environ["DATA_DIR"] = _BOOTSTRAP.name
os.environ["ALLOWED_HOSTS"] = "testserver,localhost,127.0.0.1"
os.environ["ADMIN_USERNAME"] = "test-admin"
os.environ["ADMIN_PASSWORD"] = "test-password-only"
for key in list(os.environ):
    if key.startswith("SMTP_") or key in {"PUBLIC_BASE_URL", "TRUSTED_PROXIES"}:
        os.environ.pop(key, None)

os.environ["QR_MASTER_KEY"] = secrets.token_hex(32)
os.environ["PUBLIC_BASE_URL"] = "https://testserver"
os.environ["READER_SESSION_DAYS"] = "365"

from app import config, db  # noqa: E402
from app.main import app  # noqa: E402
from app.routes import public  # noqa: E402

ADMIN = ("test-admin", "test-password-only")
VALID = dict(
    person_name="Test Person",
    house_group="TH",
    house_number="12",
    condition="Sauber",
    remark="Alles gut",
)


class AdminSessionAuth(httpx.Auth):
    """Per Anfrage anmelden, ohne anonyme Assertions desselben Clients zu verändern."""

    def __init__(self, raw):
        self.raw = raw

    def auth_flow(self, request):
        existing = request.headers.get("cookie", "")
        request.headers["cookie"] = (
            (existing + "; " if existing else "") + "raumlog_admin=" + self.raw
        )
        yield request


def admin_auth(client):
    """Echte Formularanmeldung; Sitzung für diesen isolierten Test wiederverwenden."""
    if not hasattr(client, "admin_session_auth"):
        login = TestClient(
            app, base_url=client.base_url, headers={"Origin": str(client.base_url).rstrip("/")}
        )
        try:
            page = login.get("/admin/anmelden")
            token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)[1]
            response = login.post(
                "/admin/anmelden",
                data={"username": ADMIN[0], "password": ADMIN[1], "csrf_token": token},
                follow_redirects=False,
            )
            assert response.status_code == 303
            client.admin_session_auth = AdminSessionAuth(login.cookies.get("raumlog_admin"))
        finally:
            login.close()
    return client.admin_session_auth


@pytest.fixture
def paths(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(public, "UPLOAD_DIR", upload_dir)
    import app.main as main

    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "UPLOAD_DIR", upload_dir)
    return tmp_path, upload_dir


@pytest.fixture
def client(paths):
    with TestClient(app, headers={"Origin": "http://testserver"}) as client:
        yield client
