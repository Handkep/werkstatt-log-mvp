import logging
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo
import random
import sqlite3
import shutil

from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR.parent / "data"))
DB_PATH = DATA_DIR / "app.db"
UPLOAD_DIR = DATA_DIR / "uploads"
logger = logging.getLogger("werkstatt_log")

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Zelter5 Raumlog")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

FUNNY_NAME_EXAMPLES = [
    "Albert Einstein",
    "Isaac Newton",
    "Ada Lovelace",
    "Grace Hopper",
    "Alan Turing",
    "Linus Torvalds",
    "Margaret Hamilton",
    "Marie Curie",
    "Nikola Tesla",
    "Robert C. Martin",
    "Bjarne Stroustrup",
    "Tim Berners-Lee",
    "Edsger Dijkstra",
    "Guido van Rossum",
    "Max Planck",
    "Stephen Hawking",
    "Charles Darwin",
    "Alexander Fleming",
    "Carl Friedrich Gauß",
    "Niels Bohr",

]

WORKSHOP_CONDITIONS = [
    "Sauber",
    "Aufräumen nötig",
    "Problem/Defekt",
]

ROOM_DEFINITIONS = [
    {
        "slug": "werkstatt",
        "name": "Werkstatt",
        "description": "Werkzeuge, Maschinen und Arbeitsflächen dokumentieren.",
        "intro_text": "Dokumentiere kurz die Nutzung der Werkstatt.",
        "condition_label": "Zustand der Werkstatt",
        "remark_placeholder": "z. B. Werkbank benutzt, alles sauber hinterlassen",
        "checklist_title": "Bitte die Werkstatt so verlassen",
        "checklist_intro": "Ein letzter kurzer Check hilft allen, die die Werkstatt nach dir nutzen.",
        "checklist_items": [
            "Werkzeug zurückräumen",
            "Arbeitsflächen sauber hinterlassen",
            "Müll und Restmaterial entsorgen",
            "Fenster schließen und Licht ausschalten",
            "Tür ordentlich schließen",
        ],
        "extra_fields": [],
        "sort_order": 10,
        "is_active": 1,
    },
    {
        "slug": "dachterrasse",
        "name": "Dachterrasse",
        "description": "Ordnung, Sauberkeit und Rücksicht auf die gemeinsame Terrasse festhalten.",
        "intro_text": "Dokumentiere kurz die Nutzung der Dachterrasse.",
        "condition_label": "Zustand der Dachterrasse",
        "remark_placeholder": "z. B. Stühle genutzt, alles wieder ordentlich gestellt",
        "checklist_title": "Bitte die Dachterrasse so verlassen",
        "checklist_intro": "So bleibt die Dachterrasse für alle direkt wieder nutzbar.",
        "checklist_items": [
            "Möbel ordentlich zurückstellen",
            "Tische sauber hinterlassen",
            "Leergut, Müll und Asche entfernen",
            "Licht und elektrische Geräte ausschalten",
            "Auf einen ruhigen, aufgeräumten Gesamteindruck achten",
        ],
        "extra_fields": [],
        "sort_order": 20,
        "is_active": 1,
    },
    {
        "slug": "sommerkueche",
        "name": "Sommerküche",
        "description": "Nutzung, Sauberkeit und Zustand der gemeinsamen Sommerküche erfassen.",
        "intro_text": "Dokumentiere kurz die Nutzung der Sommerküche.",
        "condition_label": "Zustand der Sommerküche",
        "remark_placeholder": "z. B. Herd benutzt, Flächen gereinigt, alles trocken hinterlassen",
        "checklist_title": "Bitte die Sommerküche so verlassen",
        "checklist_intro": "Mit ein paar Handgriffen ist die Sommerküche sofort wieder einsatzbereit.",
        "checklist_items": [
            "Benutztes Geschirr und Werkzeug reinigen",
            "Arbeitsflächen abwischen",
            "Lebensmittelreste und Müll entsorgen",
            "Wasser, Strom und Geräte prüfen",
            "Alles ordentlich und hygienisch hinterlassen",
        ],
        "extra_fields": [],
        "sort_order": 30,
        "is_active": 1,
    },
    {
        "slug": "sauna",
        "name": "Sauna",
        "description": "Sauberkeit, Nutzung und eventuelle Auffälligkeiten in der Sauna festhalten.",
        "intro_text": "Dokumentiere kurz die Nutzung der Sauna.",
        "condition_label": "Zustand der Sauna",
        "remark_placeholder": "z. B. Sauna genutzt, Holz trocken, keine Auffälligkeiten",
        "checklist_title": "Bitte die Sauna so verlassen",
        "checklist_intro": "So bleibt die Sauna hygienisch und bereit für die nächsten Nutzerinnen und Nutzer.",
        "checklist_items": [
            "Benutzte Flächen trocken hinterlassen",
            "Handtücher und persönliche Dinge mitnehmen",
            "Müll entsorgen",
            "Licht und Technik prüfen",
            "Ruhe und Sauberkeit im Raum wiederherstellen",
        ],
        "extra_fields": [],
        "sort_order": 40,
        "is_active": 1,
    },
    {
        "slug": "ruheraum",
        "name": "Ruheraum",
        "description": "Den Ruheraum ordentlich, ruhig und angenehm für die nächsten Personen dokumentieren.",
        "intro_text": "Dokumentiere kurz die Nutzung des Ruheraums.",
        "condition_label": "Zustand des Ruheraums",
        "remark_placeholder": "z. B. Matten genutzt, alles ruhig und ordentlich hinterlassen",
        "checklist_title": "Bitte den Ruheraum so verlassen",
        "checklist_intro": "Ein ruhiger und gepflegter Raum macht den Unterschied für die nächsten Personen.",
        "checklist_items": [
            "Liegen, Kissen oder Decken ordentlich zurücklegen",
            "Persönliche Dinge vollständig mitnehmen",
            "Müll entsorgen",
            "Licht und Fenster prüfen",
            "Den Raum ruhig, sauber und einladend hinterlassen",
        ],
        "extra_fields": [],
        "sort_order": 50,
        "is_active": 1,
    },
]

NAV_GROUPS = {
    "public": [
        {"id": "rooms", "label": "Räume", "href": "/"},
        {"id": "recent", "label": "Letzte Buchungen", "href": "/letzte-buchungen"},
        {"id": "notes", "label": "Anmerkungen", "href": "/anmerkungen"},
    ],
    "admin": [
        {"id": "admin", "label": "Admin", "href": "/admin"},
    ],
    "meta": [
        {"id": "privacy", "label": "Datenschutz", "href": "/datenschutz"},
    ],
}


def random_name_placeholder():
    return f"z. B. {random.choice(FUNNY_NAME_EXAMPLES)}"


def parse_json_list(raw_value: str | None):
    if not raw_value:
        return []

    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        return []

    return value if isinstance(value, list) else []


def hydrate_room(row):
    room = dict(row)
    room["checklist_items"] = parse_json_list(room.get("checklist_items_json"))
    room["extra_fields"] = parse_json_list(room.get("extra_fields_json"))
    return room


def load_active_rooms(conn):
    rows = conn.execute(
        """
        SELECT *
        FROM rooms
        WHERE is_active = 1
        ORDER BY sort_order ASC, name COLLATE NOCASE ASC
        """
    ).fetchall()
    return [hydrate_room(row) for row in rows]


def load_room_by_slug(conn, room_slug: str):
    row = conn.execute(
        "SELECT * FROM rooms WHERE slug = ? AND is_active = 1",
        (room_slug,),
    ).fetchone()
    return hydrate_room(row) if row is not None else None


def read_extra_field_values(room, form_data):
    values = {}

    for field in room.get("extra_fields", []):
        field_name = field.get("name", "").strip()
        field_label = field.get("label", field_name or "Zusatzfeld")
        field_type = field.get("type", "text")
        required = bool(field.get("required"))

        if not field_name:
            continue

        raw_value = form_data.get(field_name, "")
        value = raw_value.strip() if isinstance(raw_value, str) else ""

        if required and not value:
            raise ValueError(f"{field_label} fehlt")

        if value and field_type == "select":
            options = field.get("options", [])
            option_values = {option.get("value", "") for option in options}
            if value not in option_values:
                raise ValueError(f"{field_label} ist ungültig")

        if value:
            values[field_name] = value

    return values


def display_extra_fields(room, raw_values: str | None):
    values = {}
    if raw_values:
        try:
            parsed = json.loads(raw_values)
            if isinstance(parsed, dict):
                values = parsed
        except json.JSONDecodeError:
            values = {}

    entries = []
    for field in room.get("extra_fields", []):
        field_name = field.get("name", "").strip()
        if not field_name or field_name not in values:
            continue
        entries.append({"label": field.get("label", field_name), "value": values[field_name]})

    return entries


def build_nav(nav_section: str, nav_current: str):
    nav_groups = []
    visible_items = []

    for section_id, items in NAV_GROUPS.items():
        nav_items = []

        for item in items:
            nav_item = {
                **item,
                "section": section_id,
                "is_current": nav_current == item["id"],
            }
            nav_items.append(nav_item)

            if section_id != "meta":
                visible_items.append(nav_item)

        nav_groups.append(
            {
                "id": section_id,
                "label": section_id,
                "items": nav_items,
                "is_current_section": nav_section == section_id,
            }
        )

    return {"nav_groups": nav_groups, "nav_items": visible_items}


def page_context(request: Request, nav_section: str, nav_current: str, **kwargs):
    return {
        "request": request,
        "nav_section": nav_section,
        "nav_current": nav_current,
        "site_title": "Zelter5 Raumlog",
        **build_nav(nav_section, nav_current),
        **kwargs,
    }


def datetime_de(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return value

    return parsed.astimezone(ZoneInfo("Europe/Berlin")).strftime("%d.%m.%Y, %H:%M")


templates.env.filters["datetime_de"] = datetime_de


def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
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


@app.on_event("startup")
def on_startup():
    init_db()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def notification_enabled() -> bool:
    return all(
        [
            os.environ.get("SMTP_HOST"),
            os.environ.get("SMTP_TO"),
            os.environ.get("SMTP_FROM"),
        ]
    )


def send_usage_notification(
    *,
    room_name: str,
    person_name: str,
    house: str,
    condition: str,
    remark: str,
    started_at: str,
    image_count: int,
) -> None:
    if not notification_enabled():
        return

    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    smtp_to = os.environ["SMTP_TO"]
    smtp_from = os.environ["SMTP_FROM"]
    smtp_starttls = env_flag("SMTP_STARTTLS", True)
    smtp_ssl = env_flag("SMTP_SSL", False)

    timestamp = datetime_de(started_at)
    remark_text = remark or "Keine Bemerkung"
    image_text = f"{image_count} Bild" if image_count == 1 else f"{image_count} Bilder"

    message = EmailMessage()
    message["Subject"] = f"Neuer Werkstatt-Eintrag: {condition}"
    message["From"] = smtp_from
    message["To"] = smtp_to
    message.set_content(
        "\n".join(
            [
                "Ein neuer Werkstatt-Eintrag wurde erstellt.",
                "",
                f"Raum: {room_name}",
                f"Name: {person_name}",
                f"Haus: {house}",
                f"Zustand: {condition}",
                f"Zeit: {timestamp}",
                f"Bilder: {image_text}",
                f"Bemerkung: {remark_text}",
            ]
        )
    )

    smtp_class = smtplib.SMTP_SSL if smtp_ssl else smtplib.SMTP
    with smtp_class(smtp_host, smtp_port, timeout=15) as smtp:
        if not smtp_ssl and smtp_starttls:
            smtp.starttls()
        if smtp_user:
            smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)


def allowed_image(upload: UploadFile) -> bool:
    return upload.content_type in {"image/jpeg", "image/png", "image/webp"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    with db_connect() as conn:
        rooms = load_active_rooms(conn)

    return templates.TemplateResponse(
        "room_index.html",
        page_context(
            request,
            "public",
            "rooms",
            rooms=rooms,
        ),
    )


@app.get("/r/{room_slug}", response_class=HTMLResponse)
def room_form(request: Request, room_slug: str):
    with db_connect() as conn:
        room = load_room_by_slug(conn, room_slug)

    if room is None:
        return HTMLResponse("Raum nicht gefunden", status_code=404)

    return templates.TemplateResponse(
        "room_form.html",
        page_context(
            request,
            "public",
            "rooms",
            room=room,
            house_groups=["TH", "GH", "PH"],
            conditions=WORKSHOP_CONDITIONS,
            name_placeholder=random_name_placeholder(),
        ),
    )


@app.post("/r/{room_slug}/submit")
async def submit_usage(
    request: Request,
    room_slug: str,
    person_name: str = Form(...),
    house_group: str = Form(...),
    house_number: str = Form(...),
    condition: str = Form(...),
    remark: str = Form(""),
    images: list[UploadFile] = File(default=[]),
):
    form_data = await request.form()
    person_name = person_name.strip()
    house_group = house_group.strip().upper()
    house_number = house_number.strip()
    house = f"{house_group}{house_number}"
    condition = condition.strip()
    remark = remark.strip()

    if not person_name:
        return HTMLResponse("Name fehlt", status_code=400)

    if house_group not in {"TH", "GH", "PH"} or not house_number.isdigit():
        return HTMLResponse("Haus ungültig", status_code=400)

    if condition not in WORKSHOP_CONDITIONS:
        return HTMLResponse("Zustand ungültig", status_code=400)

    with db_connect() as conn:
        room = load_room_by_slug(conn, room_slug)

        if room is None:
            return HTMLResponse("Raum nicht gefunden", status_code=404)

        try:
            extra_field_values = read_extra_field_values(room, form_data)
        except ValueError as exc:
            return HTMLResponse(str(exc), status_code=400)

        started_at = now_iso()

        cur = conn.execute(
            """
            INSERT INTO usage_sessions (room_id, person_name, house, condition, remark, extra_fields_json, started_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                room["id"],
                person_name,
                house,
                condition,
                remark,
                json.dumps(extra_field_values, ensure_ascii=False) if extra_field_values else None,
                started_at,
            ),
        )
        session_id = cur.lastrowid

        image_count = 0

        for upload in images:
            if not upload.filename:
                continue

            if not allowed_image(upload):
                continue

            suffix = Path(upload.filename).suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
                suffix = ".img"

            filename = f"{uuid4().hex}{suffix}"
            target = UPLOAD_DIR / filename

            with target.open("wb") as f:
                shutil.copyfileobj(upload.file, f)

            conn.execute(
                """
                INSERT INTO usage_images
                (session_id, filename, original_filename, content_type, uploaded_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, filename, upload.filename, upload.content_type, now_iso()),
            )
            image_count += 1

    try:
        send_usage_notification(
            room_name=room["name"],
            person_name=person_name,
            house=house,
            condition=condition,
            remark=remark,
            started_at=started_at,
            image_count=image_count,
        )
    except Exception:
        logger.exception("Konnte Benachrichtigungs-E-Mail nicht senden")

    return RedirectResponse(f"/thanks?raum={room_slug}", status_code=303)


@app.get("/thanks", response_class=HTMLResponse)
def thanks(request: Request):
    room_slug = request.query_params.get("raum", "")

    with db_connect() as conn:
        room = load_room_by_slug(conn, room_slug) if room_slug else None
        if room is None:
            rooms = load_active_rooms(conn)
            room = rooms[0] if rooms else None

    return templates.TemplateResponse(
        "thanks.html",
        page_context(request, "public", "rooms", room=room),
    )


@app.get("/anmerkungen", response_class=HTMLResponse)
def notes(request: Request):
    with db_connect() as conn:
        entries = conn.execute(
            """
            SELECT * FROM general_notes
            ORDER BY created_at DESC
            LIMIT 20
            """
        ).fetchall()

    return templates.TemplateResponse(
        "notes.html",
        page_context(
            request,
            "public",
            "notes",
            entries=entries,
            saved=request.query_params.get("gespeichert") == "1",
            name_placeholder=random_name_placeholder(),
        ),
    )


@app.post("/anmerkungen")
def submit_note(person_name: str = Form(""), note: str = Form(...)):
    person_name = person_name.strip()
    note = note.strip()

    if not note:
        return HTMLResponse("Anmerkung fehlt", status_code=400)

    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO general_notes (person_name, note, created_at)
            VALUES (?, ?, ?)
            """,
            (person_name, note, now_iso()),
        )

    return RedirectResponse("/anmerkungen?gespeichert=1", status_code=303)


@app.get("/datenschutz", response_class=HTMLResponse)
def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", page_context(request, "meta", "privacy"))


@app.get("/letzte-buchungen", response_class=HTMLResponse)
def recent_bookings(request: Request):
    selected_room = request.query_params.get("raum", "").strip()

    with db_connect() as conn:
        rooms = load_active_rooms(conn)
        query_params = []
        where_clause = "WHERE usage_sessions.deleted_at IS NULL"

        if selected_room:
            where_clause += " AND rooms.slug = ?"
            query_params.append(selected_room)

        entries = conn.execute(
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
            LIMIT 20
            """,
            query_params,
        ).fetchall()
        entries = [dict(entry) for entry in entries]

    for entry in entries:
        filenames = entry["image_filenames"] or ""
        entry["images"] = [filename for filename in filenames.split(",") if filename]

    return templates.TemplateResponse(
        "recent_bookings.html",
        page_context(
            request,
            "public",
            "recent",
            entries=entries,
            rooms=rooms,
            selected_room=selected_room,
        ),
    )


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    selected_room = request.query_params.get("raum", "").strip()

    with db_connect() as conn:
        rooms = load_active_rooms(conn)
        query_params = []
        where_clause = "WHERE usage_sessions.deleted_at IS NULL"

        if selected_room:
            where_clause += " AND rooms.slug = ?"
            query_params.append(selected_room)

        entries = conn.execute(
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
            LIMIT 100
            """,
            query_params,
        ).fetchall()
        entries = [dict(entry) for entry in entries]

    for entry in entries:
        filenames = entry["image_filenames"] or ""
        entry["images"] = [filename for filename in filenames.split(",") if filename]

    return templates.TemplateResponse(
        "admin.html",
        page_context(
            request,
            "admin",
            "admin",
            entries=entries,
            rooms=rooms,
            selected_room=selected_room,
        ),
    )


@app.get("/admin/session/{session_id}", response_class=HTMLResponse)
def session_detail(request: Request, session_id: int):
    with db_connect() as conn:
        entry = conn.execute(
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

        images = conn.execute(
            """
            SELECT * FROM usage_images
            WHERE session_id = ?
            ORDER BY uploaded_at ASC
            """,
            (session_id,),
        ).fetchall()

    if entry is None:
        return HTMLResponse("Eintrag nicht gefunden", status_code=404)

    with db_connect() as conn:
        room = load_room_by_slug(conn, entry["room_slug"])

    entry = dict(entry)
    extra_fields = display_extra_fields(room, entry.get("extra_fields_json")) if room else []

    return templates.TemplateResponse(
        "session_detail.html",
        page_context(
            request,
            "admin",
            "admin",
            entry=entry,
            images=images,
            extra_fields=extra_fields,
        ),
    )


@app.post("/admin/session/{session_id}/delete")
def delete_session(session_id: int):
    with db_connect() as conn:
        entry = conn.execute(
            "SELECT id FROM usage_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

        if entry is None:
            return HTMLResponse("Eintrag nicht gefunden", status_code=404)

        conn.execute(
            """
            UPDATE usage_sessions
            SET deleted_at = ?
            WHERE id = ?
            """,
            (now_iso(), session_id),
        )

    return RedirectResponse("/admin", status_code=303)


@app.get("/uploads/{filename}")
def uploaded_file(filename: str):
    path = UPLOAD_DIR / filename
    if not path.exists():
        return HTMLResponse("Datei nicht gefunden", status_code=404)
    return FileResponse(path)
