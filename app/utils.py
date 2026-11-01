"""Allgemeine Hilfsfunktionen."""

import os
from datetime import UTC, datetime
from urllib.parse import urlsplit


def now_iso() -> str:
    """Gibt die aktuelle UTC-Zeit als ISO-String ohne Mikrosekunden zurück."""

    return datetime.now(UTC).isoformat(timespec="seconds")


def configured_public_base_url() -> str:
    """Nur explizite HTTP(S)-Basisadressen ohne Zugangsdaten akzeptieren."""
    value = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if value:
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or any(char.isspace() or ord(char) < 32 for char in value)
        ):
            raise ValueError(
                "PUBLIC_BASE_URL muss eine absolute HTTP(S)-URL ohne Zugangsdaten, Query oder Fragment sein"
            )
        # Löst auch einen ungültigen oder außerhalb des Bereichs liegenden Port aus.
        _ = parts.port
    return value


def safe_download_slug(value: str) -> str:
    """Erzeugt einen einfachen Dateinamenbestandteil für den PDF-Download."""

    cleaned = "".join(
        char for char in value if char.isascii() and (char.isalnum() or char in {"-", "_"})
    )
    return cleaned or "raum"
