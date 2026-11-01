"""Opt-in-Containerregressionen; ausschließlich mit temporären Testdaten."""

import base64
import io
import json
import os
import shutil
import sqlite3
import subprocess
import time
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest
from PIL import Image

from app import db
from tests.conftest import ADMIN, VALID

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DOCKER_TESTS") != "1",
    reason="Docker-Integration explizit mit RUN_DOCKER_TESTS=1 aktivieren",
)
ROOT = Path(__file__).resolve().parents[1]
IMAGE = os.environ.get("RAUMLOG_TEST_IMAGE", "werkstatt-log-mvp-werkstatt-log")


def docker(*args: str) -> str:
    return subprocess.run(
        ["docker", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=45,
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
    deadline = time.monotonic() + 20
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
        authorization = "Basic " + base64.b64encode(":".join(ADMIN).encode()).decode()
        with urlopen(
            Request(base_url + "/uploads/" + filename, headers={"Authorization": authorization}),
            timeout=5,
        ) as response:
            with Image.open(io.BytesIO(response.read())) as image:
                image.load()
                assert image.size == (24, 24)
        docker("restart", container)
        # Docker kann einen automatisch vergebenen Host-Port beim Neustart ändern.
        base_url = "http://" + docker("port", container, "8000/tcp")
        wait_for_start(container, base_url)
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
