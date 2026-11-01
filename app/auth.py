"""Authentifizierungs-Helfer für geschützte Bereiche."""

import base64
import binascii
import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic(auto_error=False)
CSRF_COOKIE = "raumlog_csrf"
CSRF_TTL = 3600


def csrf_signature(payload: str) -> str:
    """Workerübergreifender Schlüssel; ein Passwortwechsel widerruft alle Tokens."""
    key = hashlib.sha256(
        (
            os.environ.get("ADMIN_USERNAME", "") + "\0" + os.environ.get("ADMIN_PASSWORD", "")
        ).encode()
    ).digest()
    return hmac.new(key, ("admin-csrf\0" + payload).encode(), hashlib.sha256).hexdigest()


def valid_csrf_token(token: str) -> bool:
    try:
        timestamp, nonce, signature = token.split(".")
        age = time.time() - int(timestamp)
        payload = f"{timestamp}.{nonce}"
        return (
            0 <= age <= CSRF_TTL
            and len(nonce) == 64
            and secrets.compare_digest(signature, csrf_signature(payload))
        )
    except (ValueError, TypeError):
        return False


def csrf_token_for_request(request: Request) -> str:
    """Signiertes Double-Submit-Token, an ein Host-only-Cookie gebunden."""
    token = request.cookies.get(CSRF_COOKIE, "")
    if not valid_csrf_token(token):
        payload = f"{int(time.time())}.{secrets.token_hex(32)}"
        token = f"{payload}.{csrf_signature(payload)}"
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
    async with request.form(max_files=0, max_fields=2, max_part_size=1024) as form:
        token = form.get("csrf_token", "")
    cookie = request.cookies.get(CSRF_COOKIE, "")
    if (
        not isinstance(token, str)
        or not cookie
        or not valid_csrf_token(cookie)
        or not secrets.compare_digest(token.encode(), cookie.encode())
    ):
        raise HTTPException(status_code=403, detail="Ungültiges CSRF-Token. Bitte Seite neu laden.")


def require_admin(credentials: HTTPBasicCredentials | None = Depends(security)) -> None:
    """Schützt Admin-Routen per HTTP Basic Auth."""

    admin_username = os.environ.get("ADMIN_USERNAME", "")
    admin_password = os.environ.get("ADMIN_PASSWORD", "")

    if not admin_username or not admin_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin-Zugang ist nicht konfiguriert",
        )

    authenticate_header = {"WWW-Authenticate": 'Basic realm="Admin"'}
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin-Authentifizierung erforderlich",
            headers=authenticate_header,
        )

    if not admin_credentials_valid(credentials.username, credentials.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin-Zugangsdaten ungültig",
            headers=authenticate_header,
        )


def admin_credentials_valid(username: str, password: str) -> bool:
    expected_username = os.environ.get("ADMIN_USERNAME", "")
    expected_password = os.environ.get("ADMIN_PASSWORD", "")
    username_matches = secrets.compare_digest(username.encode(), expected_username.encode())
    password_matches = secrets.compare_digest(password.encode(), expected_password.encode())
    return bool(expected_username and expected_password and username_matches and password_matches)


def request_is_admin(request: Request) -> bool:
    """Optionale Anmeldung ohne Login-Challenge auf öffentlichen Formularen."""
    authorization = request.headers.get("authorization", "")
    scheme, _, payload = authorization.partition(" ")
    if scheme.lower() != "basic":
        return False
    try:
        username, password = base64.b64decode(payload, validate=True).decode("utf-8").split(":", 1)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return False
    return admin_credentials_valid(username, password)


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
