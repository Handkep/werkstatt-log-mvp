"""Template-Setup und UI-Helfer."""

import json
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR, SITE_TITLE
from app.constants import FUNNY_NAME_EXAMPLES, NAV_GROUPS

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


def page_context(request: Request, nav_section: str, nav_current: str, **kwargs) -> dict:
    """Baut den gemeinsamen Template-Kontext für alle Seiten."""

    return {
        "request": request,
        "nav_section": nav_section,
        "nav_current": nav_current,
        "site_title": SITE_TITLE,
        **build_nav(nav_section, nav_current),
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
