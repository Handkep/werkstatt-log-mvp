"""
Zelter5 Raumlog
================

Kleine FastAPI-Webanwendung zur Dokumentation der Nutzung gemeinsamer Räume
(z. B. Werkstatt, Dachterrasse, Sommerküche, Sauna, Ruheraum).

Kernfunktionen:
- Anzeige aller aktiven Räume
- QR-/Direktlink-Formular pro Raum
- Speicherung von Nutzungs-Einträgen in SQLite
- optionaler Upload von Bildern pro Eintrag
- allgemeine Anmerkungen
- einfache Admin-Ansicht mit Detailansicht und Soft-Delete
- optionale E-Mail-Benachrichtigung per SMTP

Datenhaltung:
- SQLite-Datenbank unter DATA_DIR/app.db
- Uploads unter DATA_DIR/uploads
- DATA_DIR kann per Umgebungsvariable gesetzt werden

Wichtige Hinweise:
- Die Anwendung ist bewusst klein gehalten und verwendet SQLite direkt.
- Admin-Routen sind aktuell nicht geschützt. Für produktive Nutzung sollte
  mindestens Basic Auth, Reverse-Proxy-Auth oder ein Login ergänzt werden.
- Upload-Dateien werden anhand von Content-Type und Dateiendung grob geprüft,
  aber nicht inhaltlich validiert oder neu enkodiert.
"""

import json
import logging
import os
import random
import shutil
import sqlite3
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from io import BytesIO
from urllib.parse import quote

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from fastapi.responses import StreamingResponse

from html import escape

from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from fontTools.ttLib import TTCollection
# -----------------------------------------------------------------------------
# Pfade, Verzeichnisse und globale App-Konfiguration
# -----------------------------------------------------------------------------

# Verzeichnis dieser Python-Datei, typischerweise z. B. app/main.py.
BASE_DIR = Path(__file__).resolve().parent

# DATA_DIR enthält Datenbank und Uploads. In Docker kann dieser Pfad per
# Environment-Variable auf ein persistentes Volume gelegt werden.
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR.parent / "data"))
DB_PATH = DATA_DIR / "app.db"
UPLOAD_DIR = DATA_DIR / "uploads"

logger = logging.getLogger("werkstatt_log")

# Sicherstellen, dass Daten- und Upload-Verzeichnis existieren.
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Zelter5 Raumlog")

# Jinja2 lädt HTML-Templates aus dem templates/-Ordner neben dieser Datei.
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Statische Dateien wie CSS, JS oder Bilder werden unter /static ausgeliefert.
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# -----------------------------------------------------------------------------
# Statische UI-/Formular-Daten
# -----------------------------------------------------------------------------

# Namensvorschläge für Platzhalter im Formular. Rein kosmetisch.
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

# Erlaubte Zustandswerte. Diese Werte werden sowohl im Formular angezeigt
# als auch beim Absenden serverseitig validiert.
WORKSHOP_CONDITIONS = [
    "Sauber",
    "Aufräumen nötig",
    "Problem/Defekt",
]

# Vordefinierte Räume. Beim Start werden diese in die DB geschrieben oder
# aktualisiert. Dadurch kann die Raumkonfiguration später in der DB abgefragt
# werden, bleibt aber zunächst einfach im Code pflegbar.
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

# Navigation wird zentral definiert, damit Templates nicht hart verdrahtet
# wissen müssen, welche Links existieren.
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


# -----------------------------------------------------------------------------
# Kleine Hilfsfunktionen für UI, JSON-Felder und Template-Kontext
# -----------------------------------------------------------------------------


def random_name_placeholder() -> str:
    """Erzeugt einen zufälligen Beispielnamen für Formular-Platzhalter."""

    return f"z. B. {random.choice(FUNNY_NAME_EXAMPLES)}"


def parse_json_list(raw_value: str | None) -> list:
    """
    Liest eine JSON-Liste aus einem String.

    Wird für Felder verwendet, die in SQLite als TEXT gespeichert werden,
    logisch aber Listen sind, z. B. checklist_items_json oder extra_fields_json.

    Fehlerhafte oder leere Werte werden bewusst als leere Liste behandelt,
    damit kaputte Konfigurationsdaten nicht direkt die ganze Seite crashen.
    """

    if not raw_value:
        return []

    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        return []

    return value if isinstance(value, list) else []


def hydrate_room(row: sqlite3.Row) -> dict:
    """
    Konvertiert einen Raum-Datensatz aus SQLite in ein Template-freundliches Dict.

    Die JSON-Textspalten werden dabei in echte Python-Listen umgewandelt:
    - checklist_items_json -> checklist_items
    - extra_fields_json -> extra_fields
    """

    room = dict(row)
    room["checklist_items"] = parse_json_list(room.get("checklist_items_json"))
    room["extra_fields"] = parse_json_list(room.get("extra_fields_json"))
    return room


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
    """Lädt einen aktiven Raum anhand seines Slugs, z. B. 'werkstatt'."""

    row = conn.execute(
        "SELECT * FROM rooms WHERE slug = ? AND is_active = 1",
        (room_slug,),
    ).fetchone()
    return hydrate_room(row) if row is not None else None


def read_extra_field_values(room: dict, form_data) -> dict:
    """
    Liest und validiert dynamische Zusatzfelder aus einem Formular.

    Zusatzfelder werden pro Raum über room['extra_fields'] definiert. Aktuell
    werden Textfelder und Select-Felder unterstützt. Pflichtfelder werden
    serverseitig geprüft.

    Raises:
        ValueError: Wenn ein Pflichtfeld fehlt oder ein Select-Wert ungültig ist.
    """

    values = {}

    for field in room.get("extra_fields", []):
        field_name = field.get("name", "").strip()
        field_label = field.get("label", field_name or "Zusatzfeld")
        field_type = field.get("type", "text")
        required = bool(field.get("required"))

        # Ohne technischen Feldnamen kann das Feld nicht aus dem Formular
        # gelesen werden, daher wird es ignoriert.
        if not field_name:
            continue

        raw_value = form_data.get(field_name, "")
        value = raw_value.strip() if isinstance(raw_value, str) else ""

        if required and not value:
            raise ValueError(f"{field_label} fehlt")

        # Select-Felder dürfen nur Werte annehmen, die in der Raumdefinition
        # explizit erlaubt sind. Das schützt gegen manipulierte Formulare.
        if value and field_type == "select":
            options = field.get("options", [])
            option_values = {option.get("value", "") for option in options}
            if value not in option_values:
                raise ValueError(f"{field_label} ist ungültig")

        if value:
            values[field_name] = value

    return values


def display_extra_fields(room: dict, raw_values: str | None) -> list[dict]:
    """
    Bereitet gespeicherte Zusatzfelder für die Anzeige in Templates auf.

    Aus dem gespeicherten JSON-Dict wird eine Liste aus Label/Wert-Paaren,
    damit Templates keine Kenntnis über die interne JSON-Struktur brauchen.
    """

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


def build_nav(nav_section: str, nav_current: str) -> dict:
    """
    Erstellt Navigationsdaten für Templates.

    Args:
        nav_section: Aktiver Navigationsbereich, z. B. 'public' oder 'admin'.
        nav_current: Aktiver Menüpunkt, z. B. 'rooms' oder 'recent'.

    Returns:
        Dict mit gruppierter Navigation und sichtbaren Haupt-Navigationseinträgen.
    """

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

            # Meta-Seiten wie Datenschutz werden nicht in der Hauptnavigation
            # angezeigt, bleiben aber als Gruppe verfügbar.
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


def page_context(request: Request, nav_section: str, nav_current: str, **kwargs) -> dict:
    """
    Baut den gemeinsamen Template-Kontext für alle Seiten.

    Dadurch bekommen alle Templates konsistent Zugriff auf:
    - request
    - Navigation
    - aktiven Navigationspunkt
    - Seitentitel
    - zusätzliche seitenspezifische Werte über **kwargs
    """

    return {
        "request": request,
        "nav_section": nav_section,
        "nav_current": nav_current,
        "site_title": "Zelter5 Raumlog",
        **build_nav(nav_section, nav_current),
        **kwargs,
    }


def datetime_de(value):
    """
    Jinja2-Filter: ISO-Zeitstempel in deutsches Datumsformat umwandeln.

    Erwartet ISO-Strings, die mit datetime.fromisoformat lesbar sind.
    Ungültige Werte werden unverändert zurückgegeben, damit Templates robust
    bleiben.
    """

    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return value

    return parsed.astimezone(ZoneInfo("Europe/Berlin")).strftime("%d.%m.%Y, %H:%M")


# Filter im Jinja2-Environment registrieren, nutzbar als {{ value|datetime_de }}.
templates.env.filters["datetime_de"] = datetime_de


# -----------------------------------------------------------------------------
# Datenbankzugriff und Initialisierung
# -----------------------------------------------------------------------------


def db_connect() -> sqlite3.Connection:
    """
    Erstellt eine SQLite-Verbindung mit sinnvollen Grundeinstellungen.

    row_factory=sqlite3.Row erlaubt Zugriff auf Spalten per Name.
    PRAGMA foreign_keys=ON aktiviert Fremdschlüsselprüfung in SQLite.
    PRAGMA journal_mode=WAL verbessert parallele Lesezugriffe und Robustheit.
    """

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """
    Erstellt oder migriert die SQLite-Datenbank.

    Die Funktion ist bewusst einfach gehalten:
    - Tabellen werden mit CREATE TABLE IF NOT EXISTS angelegt.
    - Fehlende Spalten werden per ALTER TABLE ergänzt.
    - Räume aus ROOM_DEFINITIONS werden per UPSERT synchronisiert.

    Für größere Projekte wäre ein Migrationswerkzeug wie Alembic sauberer.
    Für diese kleine Anwendung ist diese Variante aber unkompliziert und gut
    nachvollziehbar.
    """

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

        # Einfache additive Migration für die rooms-Tabelle.
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

        # Migration für ältere DB-Versionen der allgemeinen Anmerkungen.
        columns = conn.execute("PRAGMA table_info(general_notes)").fetchall()
        column_names = {column["name"] for column in columns}
        if "person_name" not in column_names:
            conn.execute("ALTER TABLE general_notes ADD COLUMN person_name TEXT")

        # Migration für ältere DB-Versionen der Nutzungs-Einträge.
        columns = conn.execute("PRAGMA table_info(usage_sessions)").fetchall()
        column_names = {column["name"] for column in columns}
        if "condition" not in column_names:
            conn.execute("ALTER TABLE usage_sessions ADD COLUMN condition TEXT")
        if "extra_fields_json" not in column_names:
            conn.execute("ALTER TABLE usage_sessions ADD COLUMN extra_fields_json TEXT")
        if "deleted_at" not in column_names:
            conn.execute("ALTER TABLE usage_sessions ADD COLUMN deleted_at TEXT")

        # Vordefinierte Räume synchronisieren. ON CONFLICT(slug) aktualisiert
        # bestehende Räume, ohne alte Nutzungsdaten zu verlieren.
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
def on_startup() -> None:
    """Initialisiert die Datenbank beim Start der FastAPI-Anwendung."""

    init_db()


# -----------------------------------------------------------------------------
# Zeit, Environment-Flags und E-Mail-Benachrichtigung
# -----------------------------------------------------------------------------


def now_iso() -> str:
    """Gibt die aktuelle UTC-Zeit als ISO-String ohne Mikrosekunden zurück."""

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


FONT_DIR = BASE_DIR / "static" / "fonts"


def find_ttc_subfont_index(ttc_path: Path, wanted_style: str) -> int | None:
    """
    Sucht in einer .ttc-Datei den Index eines bestimmten Schriftschnitts,
    z. B. Regular, SemiBold oder Bold.
    """
    collection = TTCollection(str(ttc_path))

    for index, font in enumerate(collection.fonts):
        styles = []

        for name in font["name"].names:
            if name.nameID in {2, 4}:  # 2 = Subfamily/Style, 4 = Full font name
                try:
                    styles.append(name.toUnicode())
                except UnicodeDecodeError:
                    pass

        joined = " ".join(styles).lower()

        if wanted_style.lower() in joined:
            return index

    return None


def register_pdf_fonts() -> dict:
    inter_ttc = FONT_DIR / "Inter.ttc"

    if inter_ttc.exists():
        regular_index = find_ttc_subfont_index(inter_ttc, "Regular")
        semibold_index = find_ttc_subfont_index(inter_ttc, "SemiBold")
        bold_index = find_ttc_subfont_index(inter_ttc, "Bold")

        if regular_index is not None and semibold_index is not None and bold_index is not None:
            try:
                pdfmetrics.registerFont(
                    TTFont("Inter-Regular", str(inter_ttc), subfontIndex=regular_index)
                )
                pdfmetrics.registerFont(
                    TTFont("Inter-SemiBold", str(inter_ttc), subfontIndex=semibold_index)
                )
                pdfmetrics.registerFont(
                    TTFont("Inter-Bold", str(inter_ttc), subfontIndex=bold_index)
                )
                pdfmetrics.registerFontFamily(
                    "Inter",
                    normal="Inter-Regular",
                    bold="Inter-Bold",
                    italic="Inter-Regular",
                    boldItalic="Inter-Bold",
                )

                return {
                    "regular": "Inter-Regular",
                    "semibold": "Inter-SemiBold",
                    "bold": "Inter-Bold",
                }
            except Exception:
                logger.exception("Inter-PDF-Schriften konnten nicht registriert werden.")

    return {
        "regular": "Helvetica",
        "semibold": "Helvetica-Bold",
        "bold": "Helvetica-Bold",
    }


PDF_FONTS = register_pdf_fonts()


def public_room_url(request: Request, room_slug: str) -> str:
    """
    Baut die öffentliche URL für einen Raum.

    Wenn PUBLIC_BASE_URL gesetzt ist, wird diese Basis-URL verwendet.
    Das ist wichtig im Produktivbetrieb hinter Docker/Caddy/Nginx.
    """
    public_base_url = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")

    if public_base_url:
        return f"{public_base_url}/r/{quote(room_slug, safe='')}"

    return str(request.url_for("room_form", room_slug=room_slug))


def make_qr_image(data: str):
    """
    Erzeugt ein QR-Code-Bild für den übergebenen Text bzw. die URL.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def draw_centered_text(pdf_canvas: canvas.Canvas, text: str, y: float, font: str, size: int) -> None:
    """
    Zeichnet eine Textzeile horizontal zentriert auf eine A4-PDF-Seite.
    """
    page_width, _ = A4
    pdf_canvas.setFont(font, size)
    text_width = pdf_canvas.stringWidth(text, font, size)
    pdf_canvas.drawString((page_width - text_width) / 2, y, text)

def draw_paragraph(
    pdf_canvas: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    font_name: str = "Helvetica",
    font_size: int = 11,
    leading: int | None = None,
    alignment=TA_CENTER,
    text_color="#111827",
) -> None:
    """
    Zeichnet einen mehrzeiligen Textblock mit sauberem Umbruch.

    Args:
        pdf_canvas: ReportLab-Zeichenfläche.
        text: Textinhalt. Normale Newlines werden zu <br/> umgewandelt.
        x: Linke X-Position des Textblocks.
        y: Untere Y-Position des Textblocks.
        width: Breite des Textblocks.
        height: Maximale Höhe des Textblocks.
        font_name: Registrierter ReportLab-Font.
        font_size: Schriftgröße in pt.
        leading: Zeilenhöhe in pt. Wenn None, wird font_size * 1.35 verwendet.
        alignment: TA_CENTER oder TA_LEFT.
        text_color: Textfarbe als Hex-Wert.
    """
    if leading is None:
        leading = int(font_size * 1.35)

    safe_text = escape(text).replace("\n", "<br/>")

    style = ParagraphStyle(
        name="PdfParagraph",
        fontName=font_name,
        fontSize=font_size,
        leading=leading,
        alignment=alignment,
        textColor=HexColor(text_color),
        spaceAfter=0,
        spaceBefore=0,
    )

    paragraph = Paragraph(safe_text, style)
    paragraph.wrapOn(pdf_canvas, width, height)
    paragraph.drawOn(pdf_canvas, x, y)

def build_room_qr_pdf(room: dict, room_url: str) -> bytes:
    """
    Erstellt ein einseitiges PDF mit QR-Code für einen Raum.
    """
    buffer = BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4

    room_name = room.get("name", "Raum")
    pdf_canvas.setTitle(f"QR-Code {room_name} - Zelter5 Raumlog")

    draw_centered_text(
        pdf_canvas,
        "Zelter5 Raumlog",
        page_height - 35 * mm,
        PDF_FONTS["bold"],
        40,
    )

    draw_centered_text(
        pdf_canvas,
        f"{room_name}",
        page_height - 48 * mm,
        PDF_FONTS["regular"],
        15,
    )

    qr_image = make_qr_image(room_url)

    qr_size = 120 * mm
    qr_x = (page_width - qr_size) / 2
    qr_y = page_height - 190 * mm

    pdf_canvas.drawImage(
        ImageReader(qr_image),
        qr_x,
        qr_y,
        width=qr_size,
        height=qr_size,
        preserveAspectRatio=True,
        mask="auto",
    )

    intro_text = (
        "Damit die Werkstatt sauber und ordentlich bleibt, bitten wir dich,\n"
        "vor der Nutzung den QR-Code zu scannen und das Formular auszufüllen."
    )

    draw_paragraph(
        pdf_canvas,
        intro_text,
        32 * mm,
        qr_y - 26 * mm,
        page_width - 64 * mm,
        24 * mm,
        font_name=PDF_FONTS["bold"],
        font_size=11,
        leading=15,
        alignment=TA_CENTER,
        text_color="#374151",
    )


    # draw_centered_text(
    #     pdf_canvas,
    #     "Bitte im jeweiligen Raum gut sichtbar anbringen.",
    #     22 * mm,
    #     "Helvetica",
    #     10,
    # )

    pdf_canvas.showPage()
    pdf_canvas.save()

    buffer.seek(0)
    return buffer.getvalue()


def safe_download_slug(value: str) -> str:
    """
    Erzeugt einen einfachen Dateinamenbestandteil für den PDF-Download.
    """
    cleaned = "".join(char for char in value if char.isalnum() or char in {"-", "_"})
    return cleaned or "raum"
# -----------------------------------------------------------------------------
# 4. Neue Route ergänzen
#    Gute Stelle: nach room_form() oder bei den öffentlichen Seiten.
# -----------------------------------------------------------------------------


@app.get("/r/{room_slug}/qr.pdf")
def room_qr_pdf(request: Request, room_slug: str):
    """
    Erstellt und liefert ein PDF mit QR-Code für einen bestimmten Raum.

    Beispiel:
        /r/werkstatt/qr.pdf
        /r/dachterrasse/qr.pdf
    """

    with db_connect() as conn:
        room = load_room_by_slug(conn, room_slug)

    if room is None:
        return HTMLResponse("Raum nicht gefunden", status_code=404)

    room_url = public_room_url(request, room_slug)
    pdf_bytes = build_room_qr_pdf(room, room_url)

    filename = f"zelter5-qr-{safe_download_slug(room_slug)}.pdf"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
    }

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers=headers,
    )


def env_flag(name: str, default: bool = False) -> bool:
    """
    Liest eine boolesche Environment-Variable.

    Als True gelten: 1, true, yes, on.
    Nicht gesetzte Variablen verwenden den übergebenen Default-Wert.
    """

    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def notification_enabled() -> bool:
    """
    Prüft, ob die minimal nötigen SMTP-Variablen gesetzt sind.

    Benötigt werden:
    - SMTP_HOST
    - SMTP_TO
    - SMTP_FROM
    """

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
    """
    Sendet optional eine E-Mail-Benachrichtigung für einen neuen Eintrag.

    Die Funktion macht nichts, wenn notification_enabled() False zurückgibt.
    SMTP-Konfiguration erfolgt vollständig über Environment-Variablen:

    Pflicht:
    - SMTP_HOST
    - SMTP_TO
    - SMTP_FROM

    Optional:
    - SMTP_PORT, Standard: 587
    - SMTP_USER
    - SMTP_PASSWORD
    - SMTP_STARTTLS, Standard: true
    - SMTP_SSL, Standard: false
    """

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


# -----------------------------------------------------------------------------
# Upload-Validierung
# -----------------------------------------------------------------------------


def allowed_image(upload: UploadFile) -> bool:
    """
    Prüft grob, ob ein Upload ein erlaubter Bildtyp ist.

    Achtung: upload.content_type kommt vom Client und ist daher keine harte
    Sicherheitsgarantie. Für eine robustere Prüfung sollte man zusätzlich den
    Dateiinhalt prüfen, z. B. mit Pillow oder python-magic.
    """

    return upload.content_type in {"image/jpeg", "image/png", "image/webp"}


# -----------------------------------------------------------------------------
# Öffentliche Seiten
# -----------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """Startseite: zeigt alle aktiven Räume als Auswahl an."""

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
    """Formularseite für einen bestimmten Raum."""

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
    """
    Verarbeitet das Nutzungsformular eines Raums.

    Ablauf:
    1. Formulardaten normalisieren und validieren.
    2. Raum aus der Datenbank laden.
    3. Optional definierte Zusatzfelder prüfen.
    4. Nutzungseintrag in usage_sessions speichern.
    5. Erlaubte Bild-Uploads in UPLOAD_DIR speichern.
    6. Upload-Metadaten in usage_images speichern.
    7. Optional E-Mail-Benachrichtigung senden.
    8. Zur Dankesseite weiterleiten.
    """

    # request.form() wird zusätzlich benötigt, weil dynamische Zusatzfelder
    # nicht als feste Funktionsparameter bekannt sind.
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

            # Nicht erlaubte Bildtypen werden still ignoriert. Alternativ könnte
            # man hier einen 400-Fehler zurückgeben, wenn striktes Verhalten
            # gewünscht ist.
            if not allowed_image(upload):
                continue

            suffix = Path(upload.filename).suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
                suffix = ".img"

            # Zufälliger Dateiname verhindert Kollisionen und verhindert, dass
            # originale Dateinamen direkt als Pfade verwendet werden.
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

    # E-Mail-Versand liegt außerhalb der DB-Transaktion. Wenn die E-Mail
    # fehlschlägt, bleibt der Eintrag trotzdem gespeichert.
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
    """
    Dankesseite nach erfolgreichem Eintrag.

    Der optionale Query-Parameter 'raum' wird genutzt, um raumspezifische
    Informationen anzuzeigen. Ist er ungültig, wird auf den ersten aktiven Raum
    zurückgefallen.
    """

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
    """Zeigt die letzten allgemeinen Anmerkungen an."""

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
    """Speichert eine allgemeine Anmerkung."""

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
    """Datenschutzseite."""

    return templates.TemplateResponse("privacy.html", page_context(request, "meta", "privacy"))


@app.get("/letzte-buchungen", response_class=HTMLResponse)
def recent_bookings(request: Request):
    """
    Öffentliche Übersicht der letzten nicht gelöschten Buchungen.

    Optionaler Query-Parameter:
    - raum=<slug> filtert auf einen bestimmten Raum.
    """

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

    # GROUP_CONCAT liefert kommagetrennte Strings. Für Templates ist eine Liste
    # praktischer.
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


# -----------------------------------------------------------------------------
# Admin-Seiten
# -----------------------------------------------------------------------------


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    """
    Admin-Übersicht der letzten nicht gelöschten Buchungen.

    Optionaler Query-Parameter:
    - raum=<slug> filtert auf einen bestimmten Raum.

    Hinweis: Diese Route ist aktuell nicht zugriffsgeschützt.
    """

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
    """
    Detailansicht eines einzelnen Nutzungs-Eintrags.

    Zeigt Grunddaten, Bemerkung, Zusatzfelder und zugehörige Bilder.
    Hinweis: Diese Route ist aktuell nicht zugriffsgeschützt.
    """

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

    # Raumdefinition erneut laden, damit dynamische Zusatzfelder mit ihren
    # Labels angezeigt werden können.
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
    """
    Markiert einen Nutzungs-Eintrag als gelöscht.

    Es handelt sich um ein Soft-Delete: Der Datensatz bleibt in der Datenbank,
    wird aber in Listen ausgeblendet, weil deleted_at gesetzt ist.
    Zugehörige Bilder bleiben ebenfalls erhalten.
    """

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


# -----------------------------------------------------------------------------
# Upload-Auslieferung
# -----------------------------------------------------------------------------


@app.get("/uploads/{filename}")
def uploaded_file(filename: str):
    """
    Liefert hochgeladene Bilder aus.

    Da Upload-Dateien beim Speichern UUID-basierte Dateinamen bekommen, ist
    das Risiko von Pfadmanipulation reduziert. Trotzdem sollte diese Route bei
    produktiver Nutzung zusätzlich gehärtet werden, z. B. durch Prüfung, dass
    der aufgelöste Pfad innerhalb von UPLOAD_DIR liegt.
    """

    path = UPLOAD_DIR / filename
    if not path.exists():
        return HTMLResponse("Datei nicht gefunden", status_code=404)
    return FileResponse(path)
