"""Opt-in-Containerregressionen; ausschließlich mit temporären Testdaten."""

import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
from contextlib import closing
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen
from uuid import uuid4

import pytest
from PIL import Image
from pypdf import PdfReader

from app import db
from tests.conftest import ADMIN, VALID

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DOCKER_TESTS") != "1",
    reason="Docker-Integration explizit mit RUN_DOCKER_TESTS=1 aktivieren",
)
ROOT = Path(__file__).resolve().parents[1]
IMAGE = os.environ.get("RAUMLOG_TEST_IMAGE", "werkstatt-log-mvp-werkstatt-log")


def docker(*args: str) -> str:
    platform = os.environ.get("RAUMLOG_TEST_PLATFORM")
    if args and args[0] == "run" and platform:
        args = ("run", "--platform", platform, *args[1:])
    return subprocess.run(
        ["docker", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=90,
    ).stdout.strip()


@pytest.fixture(scope="module", autouse=True)
def docker_available():
    if os.environ.get("RUN_DOCKER_TESTS") == "1":
        assert shutil.which("docker"), (
            "Docker ist für diese explizit aktivierten Tests erforderlich"
        )
        docker("info", "--format", "{{.ServerVersion}}")
        docker("image", "inspect", IMAGE)


def wait_for_start(container: str, base_url: str) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            with urlopen(base_url, timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            pass
        time.sleep(0.1)
    pytest.fail("Testcontainer startet nicht: " + docker("logs", container))


def test_compose_uses_matching_configurable_uid_gid():
    env = {**os.environ, "APP_UID": "2345", "APP_GID": "3456"}
    result = subprocess.run(
        ["docker", "compose", "--env-file", "/dev/null", "config", "--format", "json"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    service = json.loads(result.stdout)["services"]["werkstatt-log"]
    assert service["user"] == "2345:3456"
    assert service["cap_drop"] == ["ALL"]
    assert service["security_opt"] == ["no-new-privileges:true"]


def test_default_image_user_can_initialize_private_data():
    assert docker("image", "inspect", "--format", "{{.Config.User}}", IMAGE) == "1000:1000"
    output = docker(
        "run",
        "--rm",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        IMAGE,
        "python",
        "-c",
        "import os; from app.config import UPLOAD_DIR; from app.db import init_db; "
        "assert os.getuid() == 1000; "
        "assert int(next(line.split()[1] for line in open('/proc/self/status') "
        "if line.startswith('CapEff:')), 16) == 0; "
        "UPLOAD_DIR.mkdir(parents=True, exist_ok=True); init_db(); print('initialized')",
    )
    assert output == "initialized"


def test_image_contains_no_private_runtime_files():
    output = docker(
        "run",
        "--rm",
        "--entrypoint",
        "python",
        IMAGE,
        "-c",
        "from pathlib import Path; "
        "assert {p.name for p in Path('/app').iterdir()} == {'app', 'requirements.txt'}; "
        "assert not list(Path('/data').iterdir()); "
        "bad = [str(p) for p in Path('/app').rglob('*') "
        "if p.name.startswith('.env') or p.name in {'uploads', 'backups', '.git'} "
        "or p.suffix in {'.db', '.sqlite', '.sqlite3', '.gz', '.zip'}]; "
        "assert not bad, bad; "
        "assert list(Path('/app/app/static/fonts').rglob('*.ttf')); print('clean')",
    )
    assert output == "clean"


@pytest.mark.parametrize("existing_database", [False, True])
def test_container_writes_host_owned_data_and_survives_restart(paths, existing_database):
    assert os.getuid() != 0, "Diesen Host-Rechte-Test als unprivilegierten Benutzer ausführen"
    data_dir, upload_dir = paths
    if existing_database:
        db.init_db()
        with db.db_connect() as conn:
            conn.execute("UPDATE rooms SET name='Existing room' WHERE slug='sauna'")
            conn.execute(
                "INSERT INTO general_notes(note, created_at) VALUES ('existing note', 'now')"
            )
        (upload_dir / "existing-upload").write_bytes(b"preserve-existing-bytes")
    assert data_dir.stat().st_uid == os.getuid()
    container = docker(
        "run",
        "--detach",
        "--name",
        "raumlog-test-" + uuid4().hex,
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--mount",
        f"type=bind,source={data_dir},target=/data",
        "--publish",
        "127.0.0.1::8000",
        "--env",
        "DATA_DIR=/data",
        "--env",
        "ALLOWED_HOSTS=127.0.0.1",
        "--env",
        f"ADMIN_USERNAME={ADMIN[0]}",
        "--env",
        f"ADMIN_PASSWORD={ADMIN[1]}",
        "--env",
        "QR_MASTER_KEY=" + "ab" * 32,
        "--env",
        "PUBLIC_BASE_URL=http://127.0.0.1",
        IMAGE,
    )
    try:
        address = docker("port", container, "8000/tcp")
        base_url = "http://" + address
        wait_for_start(container, base_url)
        with urlopen(
            Request(
                base_url + "/hilfe",
                data=urlencode({"note": "container write"}).encode(),
                headers={"Origin": base_url},
            ),
            timeout=5,
        ) as response:
            assert response.status == 200
        output = io.BytesIO()
        with Image.new("RGB", (24, 24), "red") as image:
            image.save(output, "PNG")
        boundary = uuid4().hex
        parts = [
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
            for key, value in VALID.items()
        ]
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="images"; filename="test.png"\r\nContent-Type: image/png\r\n\r\n'.encode()
            + output.getvalue()
            + f"\r\n--{boundary}--\r\n".encode()
        )
        request = Request(
            base_url + "/r/werkstatt/submit",
            data=b"".join(parts),
            headers={
                "Content-Type": "multipart/form-data; boundary=" + boundary,
                "Origin": base_url,
            },
        )
        with urlopen(request, timeout=5) as response:
            assert response.status == 200
        with closing(sqlite3.connect(data_dir / "app.db")) as conn:
            assert conn.execute("SELECT count(*) FROM usage_sessions").fetchone()[0] == 1
            filename = conn.execute("SELECT filename FROM usage_images").fetchone()[0]
        stored = upload_dir / filename
        assert stored.stat().st_uid == os.getuid()
        assert stored.stat().st_mode & 0o777 == 0o600
        with pytest.raises(HTTPError) as error:
            urlopen(base_url + "/uploads/" + filename, timeout=5)
        assert error.value.code == 403
        error.value.close()
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        with opener.open(base_url + "/admin/anmelden", timeout=5) as response:
            csrf = re.search(r'name="csrf_token" value="([^"]+)"', response.read().decode())[1]
        with opener.open(
            Request(
                base_url + "/admin/anmelden",
                data=urlencode(
                    {"username": ADMIN[0], "password": ADMIN[1], "csrf_token": csrf}
                ).encode(),
                headers={"Origin": base_url},
            ),
            timeout=5,
        ) as response:
            assert response.status == 200
        with opener.open(base_url + "/uploads/" + filename, timeout=5) as response:
            with Image.open(io.BytesIO(response.read())) as image:
                image.load()
                assert image.size == (24, 24)
        # A fresh resident session must work using only a synthetic QR link.
        with opener.open(
            Request(
                base_url + "/r/werkstatt/access-link",
                data=b"",
                headers={"Origin": base_url},
            ),
            timeout=5,
        ) as response:
            qr_url = json.load(response)["url"]
        token = parse_qs(urlsplit(qr_url).fragment)["access"][0]
        resident = build_opener(HTTPCookieProcessor(CookieJar()))
        with resident.open(
            Request(
                base_url + "/r/werkstatt/access",
                data=json.dumps({"token": token}).encode(),
                headers={"Origin": base_url, "Content-Type": "application/json"},
            ),
            timeout=5,
        ) as response:
            assert response.status == 204
        with resident.open(base_url + "/logbuch", timeout=5) as response:
            assert response.status == 200
        with resident.open(base_url + "/r/sauna/qr.pdf", timeout=10) as response:
            assert "no-store" in response.headers["Cache-Control"]
            pdf = PdfReader(io.BytesIO(response.read()))
            assert len(pdf.pages) == 1
            assert ("Existing room" if existing_database else "Sauna") in pdf.pages[
                0
            ].extract_text()
        docker("restart", container)
        # Docker kann einen automatisch vergebenen Host-Port beim Neustart ändern.
        base_url = "http://" + docker("port", container, "8000/tcp")
        wait_for_start(container, base_url)
        with opener.open(base_url + "/admin", timeout=5) as response:
            assert response.status == 200 and response.url.endswith("/admin")
        with closing(sqlite3.connect(data_dir / "app.db")) as conn:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert conn.execute("SELECT count(*) FROM usage_sessions").fetchone()[0] == 1
            if existing_database:
                assert (
                    conn.execute("SELECT name FROM rooms WHERE slug='sauna'").fetchone()[0]
                    == "Existing room"
                )
                assert (
                    conn.execute("SELECT note FROM general_notes WHERE id=1").fetchone()[0]
                    == "existing note"
                )
        if existing_database:
            assert (upload_dir / "existing-upload").read_bytes() == b"preserve-existing-bytes"
    finally:
        docker("rm", "--force", container)
