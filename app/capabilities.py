"""Raumbezogene QR-Links, globale Reader-Sitzungen und globaler Widerruf."""

import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

from fastapi import HTTPException, Request, Response

from app.auth import request_is_admin
from app.config import READER_SESSION_SECONDS
from app.db import db_connect, load_room_by_slug
from app.utils import configured_public_base_url

READER_COOKIE = "raumlog_reader"
LEGACY_READER_COOKIE = "__Host-raumlog_reader"
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")
ROOM_KEY_DOMAIN = b"zelter5/room-access/v1\0"
MASTER_ID_DOMAIN = b"zelter5/reader-master-id/v1\0"


def master_key(*, required: bool = True) -> bytes | None:
    """Genau 32 kryptografisch zufällige Bytes als 64 Hex-Zeichen konfigurieren."""
    value = os.environ.get("QR_MASTER_KEY", "")
    if not value:
        if required:
            raise HTTPException(503, "Raumzugang ist nicht konfiguriert.")
        return None
    if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        # Niemals den eingelesenen Wert in Exception oder Log übernehmen.
        raise HTTPException(503, "Raumzugang ist nicht korrekt konfiguriert.")
    return bytes.fromhex(value)


def validate_capability_config() -> None:
    try:
        master_key(required=False)
    except HTTPException:
        raise ValueError("QR_MASTER_KEY muss aus genau 64 Hex-Zeichen bestehen") from None


def derive_room_token(room_id: int, key_version: int) -> str:
    """Kanonische IDs und eigene Domain: unabhängig von Namen, Sitzungen und CSRF."""
    key = master_key()
    message = ROOM_KEY_DOMAIN + f"{room_id}:{key_version}".encode("ascii")
    digest = hmac.digest(key, message, "sha256")
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def current_master_id(key: bytes) -> str:
    return hmac.digest(key, MASTER_ID_DOMAIN, "sha256").hex()


def valid_room_token(room: dict, token: str) -> bool:
    if not TOKEN_PATTERN.fullmatch(token):
        return False
    expected = derive_room_token(room["id"], room["qr_key_version"])
    return secrets.compare_digest(token, expected)


def reader_session_hash(request: Request) -> str | None:
    raw = request.cookies.get(READER_COOKIE, "")
    if not TOKEN_PATTERN.fullmatch(raw):
        return None
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def utc_timestamp() -> int:
    """UTC-Epochsekunden; in Tests kontrollierbar, ohne globale Uhr zu verändern."""
    return int(time.time())


def global_access_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT value FROM app_state WHERE key='reader_access_version'").fetchone()
    try:
        version = int(row[0]) if row else 0
    except (ValueError, TypeError):
        version = 0
    if version < 1:
        raise HTTPException(503, "Leseberechtigung ist derzeit nicht verfügbar.")
    return version


def valid_reader_session(conn: sqlite3.Connection, session_hash: str | None, now: int) -> bool:
    key = master_key(required=False)
    if key is None or session_hash is None:
        return False
    session = conn.execute(
        "SELECT master_id, expires_at, access_version FROM reader_sessions WHERE id_hash=?",
        (session_hash,),
    ).fetchone()
    return bool(
        session
        and session["expires_at"] > now
        and session["access_version"] == global_access_version(conn)
        and secrets.compare_digest(session["master_id"], current_master_id(key))
    )


def has_reader_access(conn: sqlite3.Connection, request: Request) -> bool:
    """Optionale UI-Prüfung: öffentliche Seiten verlängern keine Sitzung."""
    return request_is_admin(request) or valid_reader_session(
        conn, reader_session_hash(request), utc_timestamp()
    )


def require_reader(request: Request) -> None:
    """Zentrale Dependency für globale Reader-Routen; niemals eine Basic-Challenge."""
    if request_is_admin(request):
        return
    session_hash = reader_session_hash(request)
    with db_connect() as conn:
        if not valid_reader_session(conn, session_hash, utc_timestamp()):
            raise HTTPException(
                403, "Leseberechtigung erforderlich. Bitte einen aktuellen Raum-QR-Code scannen."
            )
    request.state.reader_session_hash = session_hash


def set_reader_cookie(
    response: Response, request: Request, raw: str, now: int, expires_at: int
) -> None:
    response.set_cookie(
        READER_COOKIE,
        raw,
        max_age=max(1, expires_at - now),
        expires=datetime.fromtimestamp(expires_at, UTC),
        path="/",
        secure=request.url.scheme == "https",
        httponly=True,
        samesite="lax",
    )


def renew_reader_session(session_hash: str) -> tuple[int, int] | None:
    """Erst für erfolgreiche Reader-Antworten; abgelaufene/widerrufene Zeilen nie reaktivieren."""
    with db_connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        now = utc_timestamp()
        key = master_key(required=False)
        if key is None:
            return None
        expires_at = now + READER_SESSION_SECONDS
        cursor = conn.execute(
            """UPDATE reader_sessions SET expires_at=? WHERE id_hash=?
            AND expires_at>? AND access_version=? AND master_id=?""",
            (expires_at, session_hash, now, global_access_version(conn), current_master_id(key)),
        )
        if cursor.rowcount != 1:
            return None
    return now, expires_at


def exchange_room_token(request: Request, room_slug: str, token: str) -> Response:
    if request.url.scheme != "https" and request.url.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise HTTPException(400, "Raumzugang benötigt eine HTTPS-Verbindung.")
    key = master_key()
    with db_connect() as conn:
        # Globale Rotation und Erteilung/Verlängerung sind eine serialisierte Transaktion.
        conn.execute("BEGIN IMMEDIATE")
        now = utc_timestamp()
        room = load_room_by_slug(conn, room_slug)
        if room is None or not valid_room_token(room, token):
            raise HTTPException(403, "QR-Zugang ungültig oder abgelaufen.")
        session_hash = reader_session_hash(request)
        current_is_valid = valid_reader_session(conn, session_hash, now)
        conn.execute("DELETE FROM reader_sessions WHERE expires_at <= ?", (now,))
        expires_at = now + READER_SESSION_SECONDS
        raw = request.cookies.get(READER_COOKIE, "")
        if current_is_valid:
            conn.execute(
                "UPDATE reader_sessions SET expires_at=? WHERE id_hash=?",
                (expires_at, session_hash),
            )
        else:
            # Unbekannte, abgelaufene und widerrufene Kennungen werden nicht wiederverwendet.
            raw = secrets.token_urlsafe(32)
            session_hash = hashlib.sha256(raw.encode("ascii")).hexdigest()
            conn.execute(
                "INSERT INTO reader_sessions(id_hash, master_id, expires_at, access_version) VALUES (?, ?, ?, ?)",
                (session_hash, current_master_id(key), expires_at, global_access_version(conn)),
            )
    response = Response(status_code=204, headers={"Cache-Control": "private, no-store"})
    set_reader_cookie(response, request, raw, now, expires_at)
    if LEGACY_READER_COOKIE in request.cookies:
        response.delete_cookie(
            LEGACY_READER_COOKIE, path="/", secure=True, httponly=True, samesite="strict"
        )
    return response


def room_qr_url(room: dict) -> str:
    base_url = configured_public_base_url()
    if not base_url:
        raise HTTPException(503, "Die öffentliche Raum-Adresse ist nicht konfiguriert.")
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(503, "Die öffentliche Raum-Adresse benötigt HTTPS.")
    token = derive_room_token(room["id"], room["qr_key_version"])
    return f"{base_url}/r/{quote(room['slug'], safe='')}#access={token}"


def rotate_all_reader_access(conn: sqlite3.Connection) -> None:
    """Alle gedruckten Tokens UND alle Sitzungen gemeinsam widerrufen."""
    master_key()
    conn.execute(
        "UPDATE app_state SET value=CAST(value AS INTEGER)+1 WHERE key='reader_access_version'"
    )
    conn.execute("UPDATE rooms SET qr_key_version=qr_key_version+1")
