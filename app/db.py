"""Datenbankzugriff und Initialisierung."""

import json
import sqlite3

from app.config import DB_PATH
from app.constants import ROOM_DEFINITIONS
from app.templating import parse_json_list
from app.utils import now_iso


def hydrate_room(row: sqlite3.Row) -> dict:
    """Konvertiert einen Raum-Datensatz in ein Template-freundliches Dict."""

    room = dict(row)
    room["checklist_items"] = parse_json_list(room.get("checklist_items_json"))
    room["extra_fields"] = parse_json_list(room.get("extra_fields_json"))
    return room


def db_connect() -> sqlite3.Connection:
    """Erstellt eine SQLite-Verbindung mit sinnvollen Grundeinstellungen."""

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def load_active_rooms(conn: sqlite3.Connection) -> list[dict]:
    """Lädt alle aktiven Räume sortiert nach sort_order und Name."""

    rows = conn.execute(
        """
        SELECT *
        FROM rooms
        WHERE is_active = 1
        ORDER BY sort_order ASC, name COLLATE NOCASE ASC
        """
    ).fetchall()
    return [hydrate_room(row) for row in rows]


def load_room_by_slug(conn: sqlite3.Connection, room_slug: str) -> dict | None:
    """Lädt einen aktiven Raum anhand seines Slugs."""

    row = conn.execute(
        "SELECT * FROM rooms WHERE slug = ? AND is_active = 1",
        (room_slug,),
    ).fetchone()
    return hydrate_room(row) if row is not None else None


def fetch_booking_entries(
    conn: sqlite3.Connection,
    *,
    selected_room: str = "",
    selected_condition: str = "",
    search: str = "",
    limit: int = 20,
) -> list[dict]:
    """Lädt Buchungseinträge mit optionalem Raumfilter."""

    query_params = []
    where_clause = "WHERE usage_sessions.deleted_at IS NULL"

    if selected_room:
        where_clause += " AND rooms.slug = ?"
        query_params.append(selected_room)

    if selected_condition:
        where_clause += " AND usage_sessions.condition = ?"
        query_params.append(selected_condition)

    if search:
        where_clause += """
            AND (
                usage_sessions.person_name LIKE ?
                OR usage_sessions.house LIKE ?
                OR usage_sessions.remark LIKE ?
                OR rooms.name LIKE ?
            )
        """
        search_term = f"%{search}%"
        query_params.extend([search_term, search_term, search_term, search_term])

    rows = conn.execute(
        f"""
        SELECT
            usage_sessions.id,
            rooms.slug AS room_slug,
            rooms.name AS room_name,
            usage_sessions.person_name,
            usage_sessions.house,
            usage_sessions.condition,
            usage_sessions.remark,
            usage_sessions.started_at,
            COUNT(usage_images.id) AS image_count,
            GROUP_CONCAT(usage_images.filename) AS image_filenames
        FROM usage_sessions
        JOIN rooms ON rooms.id = usage_sessions.room_id
        LEFT JOIN usage_images ON usage_images.session_id = usage_sessions.id
        {where_clause}
        GROUP BY usage_sessions.id
        ORDER BY usage_sessions.started_at DESC
        LIMIT ?
        """,
        [*query_params, limit],
    ).fetchall()

    entries = [dict(row) for row in rows]
    for entry in entries:
        filenames = entry["image_filenames"] or ""
        entry["images"] = [filename for filename in filenames.split(",") if filename]
    return entries


def fetch_general_notes(conn: sqlite3.Connection, *, limit: int = 20):
    """Lädt die letzten allgemeinen Anmerkungen."""

    return conn.execute(
        """
        SELECT *
        FROM general_notes
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def fetch_session_detail(conn: sqlite3.Connection, session_id: int):
    """Lädt die Detaildaten eines Nutzungs-Eintrags."""

    return conn.execute(
        """
        SELECT
            usage_sessions.id,
            rooms.name AS room_name,
            rooms.slug AS room_slug,
            usage_sessions.person_name,
            usage_sessions.house,
            usage_sessions.condition,
            usage_sessions.remark,
            usage_sessions.extra_fields_json,
            usage_sessions.started_at,
            usage_sessions.deleted_at
        FROM usage_sessions
        JOIN rooms ON rooms.id = usage_sessions.room_id
        WHERE usage_sessions.id = ?
        """,
        (session_id,),
    ).fetchone()


def fetch_session_images(conn: sqlite3.Connection, session_id: int):
    """Lädt alle Bilder zu einem Nutzungs-Eintrag."""

    return conn.execute(
        """
        SELECT *
        FROM usage_images
        WHERE session_id = ?
        ORDER BY uploaded_at ASC
        """,
        (session_id,),
    ).fetchall()


def fetch_image_by_filename(conn: sqlite3.Connection, filename: str):
    """Lädt eine gespeicherte Bildreferenz anhand des internen Dateinamens."""

    return conn.execute(
        """
        SELECT *
        FROM usage_images
        WHERE filename = ?
        """,
        (filename,),
    ).fetchone()


def soft_delete_session(conn: sqlite3.Connection, session_id: int) -> bool:
    """Markiert einen Nutzungs-Eintrag als gelöscht."""

    entry = conn.execute(
        "SELECT id FROM usage_sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if entry is None:
        return False

    conn.execute(
        """
        UPDATE usage_sessions
        SET deleted_at = ?
        WHERE id = ?
        """,
        (now_iso(), session_id),
    )
    return True


def init_db() -> None:
    """Erstellt oder migriert die SQLite-Datenbank."""

    with db_connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                intro_text TEXT,
                condition_label TEXT,
                remark_placeholder TEXT,
                checklist_title TEXT,
                checklist_intro TEXT,
                checklist_items_json TEXT,
                extra_fields_json TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS usage_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                person_name TEXT NOT NULL,
                house TEXT NOT NULL,
                condition TEXT,
                remark TEXT,
                extra_fields_json TEXT,
                started_at TEXT NOT NULL,
                deleted_at TEXT,
                FOREIGN KEY(room_id) REFERENCES rooms(id)
            );

            CREATE TABLE IF NOT EXISTS usage_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                original_filename TEXT,
                content_type TEXT,
                uploaded_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES usage_sessions(id)
            );

            CREATE TABLE IF NOT EXISTS general_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_name TEXT,
                note TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

        room_columns = conn.execute("PRAGMA table_info(rooms)").fetchall()
        room_column_names = {column["name"] for column in room_columns}
        room_column_specs = {
            "description": "TEXT",
            "intro_text": "TEXT",
            "condition_label": "TEXT",
            "remark_placeholder": "TEXT",
            "checklist_title": "TEXT",
            "checklist_intro": "TEXT",
            "checklist_items_json": "TEXT",
            "extra_fields_json": "TEXT",
            "sort_order": "INTEGER NOT NULL DEFAULT 0",
            "is_active": "INTEGER NOT NULL DEFAULT 1",
        }
        for column_name, column_type in room_column_specs.items():
            if column_name not in room_column_names:
                conn.execute(f"ALTER TABLE rooms ADD COLUMN {column_name} {column_type}")

        columns = conn.execute("PRAGMA table_info(general_notes)").fetchall()
        column_names = {column["name"] for column in columns}
        if "person_name" not in column_names:
            conn.execute("ALTER TABLE general_notes ADD COLUMN person_name TEXT")

        columns = conn.execute("PRAGMA table_info(usage_sessions)").fetchall()
        column_names = {column["name"] for column in columns}
        if "condition" not in column_names:
            conn.execute("ALTER TABLE usage_sessions ADD COLUMN condition TEXT")
        if "extra_fields_json" not in column_names:
            conn.execute("ALTER TABLE usage_sessions ADD COLUMN extra_fields_json TEXT")
        if "deleted_at" not in column_names:
            conn.execute("ALTER TABLE usage_sessions ADD COLUMN deleted_at TEXT")

        for room in ROOM_DEFINITIONS:
            conn.execute(
                """
                INSERT INTO rooms (
                    slug,
                    name,
                    description,
                    intro_text,
                    condition_label,
                    remark_placeholder,
                    checklist_title,
                    checklist_intro,
                    checklist_items_json,
                    extra_fields_json,
                    sort_order,
                    is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(slug) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    intro_text = excluded.intro_text,
                    condition_label = excluded.condition_label,
                    remark_placeholder = excluded.remark_placeholder,
                    checklist_title = excluded.checklist_title,
                    checklist_intro = excluded.checklist_intro,
                    checklist_items_json = excluded.checklist_items_json,
                    extra_fields_json = excluded.extra_fields_json,
                    sort_order = excluded.sort_order,
                    is_active = excluded.is_active
                """,
                (
                    room["slug"],
                    room["name"],
                    room["description"],
                    room["intro_text"],
                    room["condition_label"],
                    room["remark_placeholder"],
                    room["checklist_title"],
                    room["checklist_intro"],
                    json.dumps(room["checklist_items"], ensure_ascii=False),
                    json.dumps(room["extra_fields"], ensure_ascii=False),
                    room["sort_order"],
                    room["is_active"],
                ),
            )
