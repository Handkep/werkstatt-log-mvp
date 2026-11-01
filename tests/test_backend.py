import asyncio
import json
import smtplib
import sqlite3
from contextlib import closing

import pytest
from fastapi import BackgroundTasks

from app import db
from app.routes import public
from app.services import notifications
from tests.conftest import ADMIN, VALID


@pytest.mark.parametrize("number", ["²", "１２", "١٢", "1a", "-1", "1.0", "", "1" * 9])
def test_bad_house_numbers(client, number):
    assert client.post(
        "/r/werkstatt/submit", data={**VALID, "house_number": number}
    ).status_code == (422 if not number else 400)


@pytest.mark.parametrize("number", ["1", "0012", "12345678"])
def test_ascii_house_numbers_and_html_limit(client, number):
    assert 'pattern="[0-9]+" maxlength="8"' in client.get("/r/werkstatt").text
    assert (
        client.post(
            "/r/werkstatt/submit", data={**VALID, "house_number": number}, follow_redirects=False
        ).status_code
        == 303
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("person_name", "  "),
        ("person_name", "x" * 101),
        ("remark", "x" * 2001),
        ("condition", "unknown"),
        ("house_group", "XX"),
    ],
)
def test_form_validation(client, field, value):
    assert client.post("/r/werkstatt/submit", data={**VALID, field: value}).status_code == 400


def test_empty_and_missing_note_and_unknown_room(client):
    assert client.post("/hilfe", data={"note": "  "}).status_code == 400
    assert client.post("/hilfe", data={"note": "x" * 4001}).status_code == 400
    assert client.post("/hilfe", data={"note": "ok", "person_name": "x" * 101}).status_code == 400
    assert client.get("/r/missing").status_code == 404
    assert client.post("/r/missing/submit", data=VALID).status_code == 404
    assert client.post("/r/werkstatt/submit", data={}).status_code == 422


def test_extra_fields_and_qr_entry(client):
    fields = [
        {
            "name": "issue",
            "label": "Problem",
            "required": True,
            "type": "select",
            "options": [{"value": "ok", "label": "Okay"}],
        }
    ]
    with db.db_connect() as conn:
        conn.execute(
            "UPDATE rooms SET extra_fields_json=? WHERE slug='sauna'", (json.dumps(fields),)
        )
    assert client.post("/r/sauna/submit", data=VALID).status_code == 400
    assert client.post("/r/sauna/submit", data={**VALID, "issue": "other"}).status_code == 400
    response = client.post(
        "/r/sauna/submit?mode=room", data={**VALID, "issue": "ok"}, follow_redirects=False
    )
    assert response.headers["location"] == "/thanks?raum=sauna"
    assert "Okay" in client.get("/r/sauna").text
    assert "Problem" in client.get("/admin/session/1", auth=ADMIN).text


def test_db_transactions_commit_rollback_close(client):
    with db.db_connect() as conn:
        conn.execute("INSERT INTO general_notes(note, created_at) VALUES ('committed', 'now')")
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")
    with pytest.raises(RuntimeError):
        with db.db_connect() as rollback_conn:
            rollback_conn.execute(
                "INSERT INTO general_notes(note, created_at) VALUES ('rollback', 'now')"
            )
            raise RuntimeError("abort")
    with pytest.raises(sqlite3.ProgrammingError):
        rollback_conn.execute("SELECT 1")
    with db.db_connect() as conn:
        assert conn.execute("SELECT note FROM general_notes").fetchall()[0][0] == "committed"
        assert conn.execute("SELECT count(*) FROM general_notes").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_db_init_preserves_edits_deactivation_and_empty_configuration(client):
    with db.db_connect() as conn:
        conn.execute(
            "UPDATE rooms SET name='Custom', is_active=0, sort_order=123 WHERE slug='sauna'"
        )
        conn.execute("DELETE FROM rooms WHERE slug='ruheraum'")
    db.init_db()
    db.init_db()
    with db.db_connect() as conn:
        row = conn.execute("SELECT * FROM rooms WHERE slug='sauna'").fetchone()
        assert (row["name"], row["is_active"], row["sort_order"]) == ("Custom", 0, 123)
        assert conn.execute("SELECT count(*) FROM rooms").fetchone()[0] == 4
        conn.execute("DELETE FROM rooms")
    db.init_db()
    with db.db_connect() as conn:
        assert conn.execute("SELECT count(*) FROM rooms").fetchone()[0] == 0


def test_legacy_schema_migration_is_additive(paths):
    with closing(sqlite3.connect(db.DB_PATH)) as conn, conn:
        conn.executescript("""
            CREATE TABLE rooms(id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL);
            CREATE TABLE usage_sessions(id INTEGER PRIMARY KEY, room_id INTEGER NOT NULL, person_name TEXT NOT NULL, house TEXT NOT NULL, remark TEXT, started_at TEXT NOT NULL);
            CREATE TABLE usage_images(id INTEGER PRIMARY KEY, session_id INTEGER, filename TEXT, original_filename TEXT, content_type TEXT, uploaded_at TEXT);
            CREATE TABLE general_notes(id INTEGER PRIMARY KEY, note TEXT NOT NULL, created_at TEXT NOT NULL);
            INSERT INTO rooms VALUES(42, 'legacy', 'Legacy Room');
            INSERT INTO usage_sessions VALUES(7, 42, 'Old Name', 'TH1', 'Old remark', '2026-01-01');
            INSERT INTO usage_images VALUES(3, 7, 'old.png', 'old.png', 'image/png', '2026-01-01');
            INSERT INTO general_notes VALUES(9, 'Old Note', '2026-01-01');
        """)
    old_file = paths[1] / "old.png"
    old_file.write_bytes(b"unchanged")
    db.init_db()
    db.init_db()
    with db.db_connect() as conn:
        assert conn.execute("SELECT count(*) FROM rooms").fetchone()[0] == 1
        assert (
            conn.execute("SELECT person_name FROM usage_sessions WHERE id=7").fetchone()[0]
            == "Old Name"
        )
        assert db.fetch_image_by_filename(conn, "old.png") is not None
        assert conn.execute("SELECT note FROM general_notes WHERE id=9").fetchone()[0] == "Old Note"
        assert [row[0] for row in conn.execute("SELECT version FROM schema_migrations")] == [
            1,
            2,
            3,
            4,
        ]
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    assert old_file.read_bytes() == b"unchanged"


def test_smtp_failure_after_commit(client, monkeypatch, caplog):
    committed = []

    def fail(**kwargs):
        with db.db_connect() as conn:
            committed.append(conn.execute("SELECT count(*) FROM usage_sessions").fetchone()[0])
        raise smtplib.SMTPException("SECRET SMTP RESPONSE")

    monkeypatch.setattr(notifications, "send_usage_notification", fail)
    assert client.post("/r/werkstatt/submit", data=VALID, follow_redirects=False).status_code == 303
    assert committed == [1]
    assert "SECRET SMTP RESPONSE" not in caplog.text
    assert "Benachrichtigung fehlgeschlagen" in caplog.text


def test_background_task_not_in_http_response_path(client, monkeypatch):
    queued = []

    def capture(self, func, *args, **kwargs):
        queued.append((func, kwargs))

    monkeypatch.setattr(BackgroundTasks, "add_task", capture)
    client.post("/r/werkstatt/submit", data=VALID)
    assert len(queued) == 1
    assert queued[0][0] is notifications.notify_usage_safely


def test_blocking_operations_are_off_event_loop(client, monkeypatch):
    original = public.validate_image_uploads

    def check(images):
        with pytest.raises(RuntimeError):
            asyncio.get_running_loop()
        return original(images)

    monkeypatch.setattr(public, "validate_image_uploads", check)
    assert client.post("/r/werkstatt/submit", data=VALID).status_code == 200


def test_database_errors_are_generic(client, monkeypatch, caplog):
    def fail(*args):
        raise sqlite3.OperationalError("SECRET SQL DATA")

    monkeypatch.setattr(public, "load_active_rooms", fail)
    response = client.get("/")
    assert response.status_code == 503
    assert "SECRET" not in response.text + caplog.text


def test_smtp_uses_room_name(monkeypatch):
    messages = []
    for key, value in {
        "SMTP_HOST": "example.test",
        "SMTP_FROM": "a@example.test",
        "SMTP_TO": "b@example.test",
    }.items():
        monkeypatch.setenv(key, value)

    class SMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self, **kwargs):
            assert kwargs["context"].verify_mode

        def send_message(self, message):
            messages.append(message)

    monkeypatch.setattr(notifications.smtplib, "SMTP", SMTP)
    notifications.send_usage_notification(
        room_name="Sauna",
        person_name="Test",
        house="TH1",
        condition="Sauber",
        remark="",
        started_at="2026-01-01T12:00:00+00:00",
        image_count=0,
    )
    assert "Sauna" in messages[0]["Subject"]
    assert "Werkstatt" not in messages[0].get_content()


def test_soft_delete_is_atomic_and_does_not_change_timestamp(client):
    from concurrent.futures import ThreadPoolExecutor

    client.post("/r/werkstatt/submit", data=VALID)

    def delete(_):
        with db.db_connect() as conn:
            return db.soft_delete_session(conn, 1)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(delete, range(8)))
    assert results.count(True) == 1


def test_concurrent_initialization_seeds_only_once(paths):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: db.init_db(), range(4)))
    with db.db_connect() as conn:
        assert conn.execute("SELECT count(*) FROM rooms").fetchone()[0] == 5


def test_redirect_preserves_custom_room_slug(client):
    with db.db_connect() as conn:
        conn.execute("INSERT INTO rooms(slug, name) VALUES ('special.ä', 'Special')")
    response = client.post("/r/special.%C3%A4/submit", data=VALID, follow_redirects=False)
    assert response.headers["location"] == "/thanks?raum=special.%C3%A4"
    assert client.get(response.headers["location"]).status_code == 200
