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


def configured_public_scheme(host: str) -> str | None:
    """Protokoll aus fester Außenadresse, nur bei exakt passendem Host und Port.

    Fehlender Port entspricht dem Standardport des öffentlichen Protokolls,
    nicht dem internen HTTP-Port nach TLS-Terminierung. Forwarding-Header sind
    hierfür keine Quelle. Andere erlaubte Hosts behalten ihre Transportdaten.
    """
    base = configured_public_base_url()
    if not base:
        return None
    try:
        public = urlsplit(base)
        incoming = urlsplit("//" + host)
        if (
            not incoming.hostname
            or incoming.username is not None
            or incoming.password is not None
            or incoming.path
            or incoming.query
            or incoming.fragment
            or any(char.isspace() or ord(char) < 32 or char == "\\" for char in host)
        ):
            return None
        public_host = public.hostname.encode("idna").decode("ascii").lower()
        incoming_host = incoming.hostname.encode("idna").decode("ascii").lower()
        default = 443 if public.scheme == "https" else 80
        incoming_port = incoming.port if incoming.port is not None else default
        public_port = public.port if public.port is not None else default
        if incoming_host != public_host or incoming_port != public_port:
            return None
        return public.scheme
    except (ValueError, UnicodeError):
        return None
