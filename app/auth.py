"""Authentifizierungs-Helfer für geschützte Bereiche."""

import hashlib
import hmac
import os
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit

from fastapi import HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

CSRF_COOKIE = "raumlog_csrf"
CSRF_TTL = 3600
ADMIN_COOKIE = "raumlog_admin"
ADMIN_SESSION_SECONDS = 8 * 3600
SESSION_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")
ADMIN_DOCUMENT = re.compile(r"/admin(?:/?|/nachrichten|/raumzugaenge|/logbuch|/session/[0-9]+)")


def csrf_signature(payload: str, binding: str = "login") -> str:
    """Workerübergreifender Schlüssel; ein Passwortwechsel widerruft alle Tokens."""
    key = hashlib.sha256(
        (
            os.environ.get("ADMIN_USERNAME", "") + "\0" + os.environ.get("ADMIN_PASSWORD", "")
        ).encode()
    ).digest()
    return hmac.new(
        key, ("admin-csrf\0" + binding + "\0" + payload).encode(), hashlib.sha256
    ).hexdigest()


def valid_csrf_token(token: str, binding: str = "login") -> bool:
    try:
        timestamp, nonce, signature = token.split(".")
        age = time.time() - int(timestamp)
        payload = f"{timestamp}.{nonce}"
        return (
            0 <= age <= CSRF_TTL
            and len(nonce) == 64
            and secrets.compare_digest(signature, csrf_signature(payload, binding))
        )
    except (ValueError, TypeError):
        return False


def csrf_token_for_request(request: Request) -> str:
    """Signiertes Double-Submit-Token, an ein Host-only-Cookie gebunden."""
    binding = csrf_binding(request)
    token = request.cookies.get(CSRF_COOKIE, "")
    if not valid_csrf_token(token, binding):
        payload = f"{int(time.time())}.{secrets.token_hex(32)}"
        token = f"{payload}.{csrf_signature(payload, binding)}"
    return token


def issue_csrf_token(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        CSRF_COOKIE,
        token,
        max_age=CSRF_TTL,
        path="/admin",
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
    )


async def require_admin_csrf(request: Request) -> None:
    """Routerweite Prüfung für jede zustandsändernde Admin-Methode."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    async with request.form(max_files=0, max_fields=4, max_part_size=4096) as form:
        token = form.get("csrf_token", "")
    cookie = request.cookies.get(CSRF_COOKIE, "")
    binding = await run_in_threadpool(csrf_binding, request)
    if (
        not isinstance(token, str)
        or not cookie
        or not valid_csrf_token(cookie, binding)
        or not secrets.compare_digest(token.encode(), cookie.encode())
    ):
        raise HTTPException(status_code=403, detail="Ungültiges CSRF-Token. Bitte Seite neu laden.")


def admin_configured() -> bool:
    return bool(os.environ.get("ADMIN_USERNAME") and os.environ.get("ADMIN_PASSWORD"))


def require_admin(request: Request) -> None:
    if not admin_configured():
        raise HTTPException(503, "Admin-Zugang ist nicht konfiguriert")
    if request_is_admin(request):
        return
    if (
        request.method in {"GET", "HEAD"}
        and ADMIN_DOCUMENT.fullmatch(request.url.path)
        and "text/html" in request.headers.get("accept", "").lower()
    ):
        target = safe_admin_next(
            request.url.path + ("?" + request.url.query if request.url.query else "")
        )
        raise HTTPException(
            303,
            "Bitte anmelden",
            headers={"Location": "/admin/anmelden?" + urlencode({"next": target})},
        )
    raise HTTPException(401, "Admin-Anmeldung erforderlich")


def safe_admin_next(value: str) -> str:
    if any(ord(char) < 32 or ord(char) == 127 for char in value) or "\\" in value:
        return "/admin"
    try:
        parts = urlsplit(value)
        if (
            parts.scheme
            or parts.netloc
            or parts.fragment
            or not ADMIN_DOCUMENT.fullmatch(parts.path)
        ):
            return "/admin"
    except ValueError:
        return "/admin"
    return value


def admin_credentials_valid(username: str, password: str) -> bool:
    expected_username = os.environ.get("ADMIN_USERNAME", "")
    expected_password = os.environ.get("ADMIN_PASSWORD", "")
    username_matches = secrets.compare_digest(username.encode(), expected_username.encode())
    password_matches = secrets.compare_digest(password.encode(), expected_password.encode())
    return bool(expected_username and expected_password and username_matches and password_matches)


def admin_session_hash(request: Request) -> str | None:
    raw = request.cookies.get(ADMIN_COOKIE, "")
    if not SESSION_PATTERN.fullmatch(raw):
        return None
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def credential_id(secret: str) -> str:
    credentials = os.environ.get("ADMIN_USERNAME", "") + "\0" + os.environ.get("ADMIN_PASSWORD", "")
    return hmac.new(
        secret.encode(), ("admin-credentials\0" + credentials).encode(), hashlib.sha256
    ).hexdigest()


def request_is_admin(request: Request) -> bool:
    """Nur serverseitige Sitzungen; Basic-Header gewähren keinen Zugang mehr."""
    if hasattr(request.state, "admin_authenticated"):
        return request.state.admin_authenticated
    digest = admin_session_hash(request)
    authenticated = False
    if digest and admin_configured():
        # Lokaler Import vermeidet den bestehenden Zyklus db -> templating -> auth.
        from app.db import db_connect

        with db_connect() as conn:
            row = conn.execute(
                "SELECT credential_id, expires_at FROM admin_sessions WHERE id_hash=?", (digest,)
            ).fetchone()
            secret = conn.execute(
                "SELECT value FROM app_state WHERE key='rate_limit_secret'"
            ).fetchone()[0]
            authenticated = bool(
                row
                and row["expires_at"] > int(time.time())
                and secrets.compare_digest(row["credential_id"], credential_id(secret))
            )
    request.state.admin_authenticated = authenticated
    return authenticated


def csrf_binding(request: Request) -> str:
    return admin_session_hash(request) if request_is_admin(request) else "login"


def create_admin_session(request: Request, response: Response) -> None:
    from app.db import db_connect

    raw = secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw.encode("ascii")).hexdigest()
    with db_connect() as conn:
        secret = conn.execute(
            "SELECT value FROM app_state WHERE key='rate_limit_secret'"
        ).fetchone()[0]
        conn.execute(
            "DELETE FROM admin_sessions WHERE expires_at <= ? OR id_hash=?",
            (int(time.time()), admin_session_hash(request)),
        )
        conn.execute(
            "INSERT INTO admin_sessions VALUES (?, ?, ?)",
            (digest, credential_id(secret), int(time.time()) + ADMIN_SESSION_SECONDS),
        )
    response.set_cookie(
        ADMIN_COOKIE,
        raw,
        path="/",
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
    )
    response.delete_cookie(CSRF_COOKIE, path="/admin")


def revoke_admin_session(request: Request, response: Response) -> None:
    from app.db import db_connect

    with db_connect() as conn:
        conn.execute("DELETE FROM admin_sessions WHERE id_hash=?", (admin_session_hash(request),))
    response.delete_cookie(ADMIN_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/admin")


def _origin(value: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            return None
        return (
            parsed.scheme,
            parsed.hostname.lower(),
            parsed.port or (443 if parsed.scheme == "https" else 80),
        )
    except ValueError:
        return None


def require_same_origin(request: Request) -> None:
    """Strikter Browserschutz: Origin oder nicht fälschbare Same-Origin-Fetch-Metadaten."""
    site = request.headers.get("sec-fetch-site")
    origin = request.headers.get("origin")
    expected = _origin(f"{request.url.scheme}://{request.url.netloc}")
    if expected is None or (site is not None and site != "same-origin"):
        raise HTTPException(403, "Anfrage von fremder Herkunft abgelehnt.")
    if origin not in {None, "null"} and _origin(origin) != expected:
        raise HTTPException(403, "Anfrage von fremder Herkunft abgelehnt.")
    # Referrer-Policy=no-referrer kann bei HTML-Navigation Origin=null verursachen.
    if site == "same-origin" or (origin not in {None, "null"} and _origin(origin) == expected):
        return
    raise HTTPException(403, "Herkunft der Anfrage konnte nicht bestätigt werden.")
