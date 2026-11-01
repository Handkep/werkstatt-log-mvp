"""Template-Setup und UI-Helfer."""

import hashlib
import json
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.auth import request_is_admin
from app.config import BASE_DIR, LIMITS, SITE_TITLE
from app.constants import FUNNY_NAME_EXAMPLES, NAV_GROUPS

# Ein gemeinsamer Inhalts-Hash umfasst auch per @import geladene Stylesheets.
ASSET_VERSION = hashlib.sha256(
    b"".join(
        path.read_bytes()
        for path in sorted((BASE_DIR / "static").rglob("*"))
        if path.suffix in {".js", ".css"}
    )
).hexdigest()[:12]

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def random_name_placeholder() -> str:
    """Erzeugt einen zufälligen Beispielnamen für Formular-Platzhalter."""

    return f"z. B. {random.choice(FUNNY_NAME_EXAMPLES)}"


def parse_json_list(raw_value: str | None) -> list:
    """Liest eine JSON-Liste robust aus einem String."""

    if not raw_value:
        return []

    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        return []

    return value if isinstance(value, list) else []


def display_extra_fields(room: dict, raw_values: str | None) -> list[dict]:
    """
    Bereitet gespeicherte Zusatzfelder für die Anzeige in Templates auf.
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
    """Erstellt Navigationsdaten für Templates."""

    def items(section: str) -> list[dict]:
        return [{**item, "is_current": nav_current == item["id"]} for item in NAV_GROUPS[section]]

    return {
        "nav_items": items("public"),
        "admin_items": items("admin"),
        "admin_section_active": nav_section == "admin",
    }


def page_context(request: Request, nav_section: str, nav_current: str, **kwargs) -> dict:
    """Baut den gemeinsamen Template-Kontext für alle Seiten."""

    admin_authenticated = request_is_admin(request)
    navigation = build_nav(nav_section, nav_current)
    for item in navigation["nav_items"]:
        if item["id"] == "logbook" and admin_authenticated:
            item["href"] = "/admin/logbuch"
        if item["id"] == "rooms" and request.url.path.startswith("/r/"):
            item["label"] = "Alle Räume"
    return {
        "request": request,
        "admin_authenticated": admin_authenticated,
        "nav_section": nav_section,
        "nav_current": nav_current,
        "site_title": SITE_TITLE,
        "asset_version": ASSET_VERSION,
        "csp_nonce": getattr(request.state, "csp_nonce", ""),
        "limits": LIMITS,
        **navigation,
        **kwargs,
    }


def datetime_de(value):
    """Jinja2-Filter: ISO-Zeitstempel in deutsches Datumsformat umwandeln."""

    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return value

    return parsed.astimezone(ZoneInfo("Europe/Berlin")).strftime("%d.%m.%Y, %H:%M")


templates.env.filters["datetime_de"] = datetime_de
