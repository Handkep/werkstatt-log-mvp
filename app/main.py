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


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR.parent / "data"))
DB_PATH = DATA_DIR / "app.db"
UPLOAD_DIR = DATA_DIR / "uploads"
logger = logging.getLogger("werkstatt_log")

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Werkstatt Log MVP")
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


def random_name_placeholder():
    return f"z. B. {random.choice(FUNNY_NAME_EXAMPLES)}"


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
                name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS usage_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                person_name TEXT NOT NULL,
                house TEXT NOT NULL,
                condition TEXT,
                remark TEXT,
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

            INSERT OR IGNORE INTO rooms (slug, name)
            VALUES ('werkstatt', 'Werkstatt');
            """
        )

        columns = conn.execute("PRAGMA table_info(general_notes)").fetchall()
        column_names = {column["name"] for column in columns}
        if "person_name" not in column_names:
            conn.execute("ALTER TABLE general_notes ADD COLUMN person_name TEXT")

        columns = conn.execute("PRAGMA table_info(usage_sessions)").fetchall()
        column_names = {column["name"] for column in columns}
        if "condition" not in column_names:
            conn.execute("ALTER TABLE usage_sessions ADD COLUMN condition TEXT")
        if "deleted_at" not in column_names:
            conn.execute("ALTER TABLE usage_sessions ADD COLUMN deleted_at TEXT")


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
def index():
    return RedirectResponse("/r/werkstatt", status_code=303)


@app.get("/r/{room_slug}", response_class=HTMLResponse)
def room_form(request: Request, room_slug: str):
    with db_connect() as conn:
        room = conn.execute(
            "SELECT * FROM rooms WHERE slug = ?",
            (room_slug,),
        ).fetchone()

    if room is None:
        return HTMLResponse("Raum nicht gefunden", status_code=404)

    return templates.TemplateResponse(
        "room_form.html",
        {
            "request": request,
            "room": room,
            "house_groups": ["TH", "GH", "PH"],
            "conditions": WORKSHOP_CONDITIONS,
            "name_placeholder": random_name_placeholder(),
        },
    )


@app.post("/r/{room_slug}/submit")
async def submit_usage(
    room_slug: str,
    person_name: str = Form(...),
    house_group: str = Form(...),
    house_number: str = Form(...),
    condition: str = Form(...),
    remark: str = Form(""),
    images: list[UploadFile] = File(default=[]),
):
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
        room = conn.execute(
            "SELECT * FROM rooms WHERE slug = ?",
            (room_slug,),
        ).fetchone()

        if room is None:
            return HTMLResponse("Raum nicht gefunden", status_code=404)

        started_at = now_iso()

        cur = conn.execute(
            """
            INSERT INTO usage_sessions (room_id, person_name, house, condition, remark, started_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (room["id"], person_name, house, condition, remark, started_at),
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

    return RedirectResponse("/thanks", status_code=303)


@app.get("/thanks", response_class=HTMLResponse)
def thanks(request: Request):
    return templates.TemplateResponse("thanks.html", {"request": request})


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
        {
            "request": request,
            "entries": entries,
            "saved": request.query_params.get("gespeichert") == "1",
            "name_placeholder": random_name_placeholder(),
        },
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
    return templates.TemplateResponse("privacy.html", {"request": request})


@app.get("/letzte-buchungen", response_class=HTMLResponse)
def recent_bookings(request: Request):
    with db_connect() as conn:
        entries = conn.execute(
            """
            SELECT
                usage_sessions.id,
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
            WHERE usage_sessions.deleted_at IS NULL
            GROUP BY usage_sessions.id
            ORDER BY usage_sessions.started_at DESC
            LIMIT 20
            """
        ).fetchall()
        entries = [dict(entry) for entry in entries]

    for entry in entries:
        filenames = entry["image_filenames"] or ""
        entry["images"] = [filename for filename in filenames.split(",") if filename]

    return templates.TemplateResponse(
        "recent_bookings.html",
        {
            "request": request,
            "entries": entries,
        },
    )


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    with db_connect() as conn:
        entries = conn.execute(
            """
            SELECT
                usage_sessions.id,
                rooms.name AS room_name,
                usage_sessions.person_name,
                usage_sessions.house,
                usage_sessions.condition,
                usage_sessions.remark,
                usage_sessions.started_at,
                COUNT(usage_images.id) AS image_count
            FROM usage_sessions
            JOIN rooms ON rooms.id = usage_sessions.room_id
            LEFT JOIN usage_images ON usage_images.session_id = usage_sessions.id
            WHERE usage_sessions.deleted_at IS NULL
            GROUP BY usage_sessions.id
            ORDER BY usage_sessions.started_at DESC
            LIMIT 100
            """
        ).fetchall()

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "entries": entries,
        },
    )


@app.get("/admin/session/{session_id}", response_class=HTMLResponse)
def session_detail(request: Request, session_id: int):
    with db_connect() as conn:
        entry = conn.execute(
            """
            SELECT
                usage_sessions.id,
                rooms.name AS room_name,
                usage_sessions.person_name,
                usage_sessions.house,
                usage_sessions.condition,
                usage_sessions.remark,
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

    return templates.TemplateResponse(
        "session_detail.html",
        {
            "request": request,
            "entry": entry,
            "images": images,
        },
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
