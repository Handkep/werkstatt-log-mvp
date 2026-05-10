"""Allgemeine Hilfsfunktionen."""

import os
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import Request


def now_iso() -> str:
    """Gibt die aktuelle UTC-Zeit als ISO-String ohne Mikrosekunden zurück."""

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def safe_download_slug(value: str) -> str:
    """Erzeugt einen einfachen Dateinamenbestandteil für den PDF-Download."""

    cleaned = "".join(char for char in value if char.isalnum() or char in {"-", "_"})
    return cleaned or "raum"
