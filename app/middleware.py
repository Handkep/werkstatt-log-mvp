"""ASGI-Grenzen vor dem Multipart-Parser und datensparsame Sicherheitsheader."""

import asyncio
import hashlib
import hmac
import ipaddress
import re
import secrets
import sqlite3
import time

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.auth import issue_csrf_token
from app.capabilities import READER_COOKIE, renew_reader_session, set_reader_cookie
from app.config import (
    MAX_REQUEST_SIZE_BYTES,
    RATE_LIMIT_COUNT,
    RATE_LIMIT_GLOBAL_COUNT,
    RATE_LIMIT_WINDOW_SECONDS,
    REQUEST_BODY_TIMEOUT_SECONDS,
    TRUSTED_PROXY_NETWORKS,
)
from app.db import db_connect
from app.public_errors import public_failure
from app.utils import configured_public_scheme

PUBLIC_SUBMISSION = re.compile(r"^/r/[^/]+/(submit|access)/?$")


def consume_rate_limit(client: str, *, namespace: str = "public") -> int:
    """Atomare, persistente Fenster; keine IPs im Klartext. Fehler sind fail-closed."""
    now = int(time.time())
    with db_connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        secret = conn.execute(
            "SELECT value FROM app_state WHERE key='rate_limit_secret'"
        ).fetchone()[0]
        identity = client if namespace == "public" else namespace + ":" + client
        digest = hmac.new(secret.encode(), identity.encode(), hashlib.sha256).hexdigest()
        conn.execute("DELETE FROM rate_limits WHERE expires_at <= ?", (now,))
        global_bucket = "global" if namespace == "public" else namespace + ":global"
        buckets = [(digest, RATE_LIMIT_COUNT), (global_bucket, RATE_LIMIT_GLOBAL_COUNT)]
        for bucket, limit in buckets:
            row = conn.execute(
                "SELECT count, expires_at FROM rate_limits WHERE bucket=?", (bucket,)
            ).fetchone()
            if row and row["count"] >= limit:
                return max(1, row["expires_at"] - now)
        for bucket, _ in buckets:
            conn.execute(
                """INSERT INTO rate_limits VALUES (?, 1, ?)
                ON CONFLICT(bucket) DO UPDATE SET count=count+1""",
                (bucket, now + RATE_LIMIT_WINDOW_SECONDS),
            )
    return 0


class RequestProtectionMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app
        self.trusted_proxies = [ipaddress.ip_network(value) for value in TRUSTED_PROXY_NETWORKS]

    def trusted(self, value: str) -> bool:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return False
        return any(address in network for network in self.trusted_proxies)

    def apply_proxy_headers(self, scope: Scope, headers: Headers) -> str:
        client = scope.get("client")
        address = client[0] if client else "unknown"
        if self.trusted(address):
            chain = headers.get("x-forwarded-for", "").split(",")
            for candidate in reversed(chain):
                if not self.trusted(address):
                    break
                try:
                    address = str(ipaddress.ip_address(candidate.strip()))
                except ValueError:
                    break
            proto = headers.get("x-forwarded-proto", "")
            if proto in {"http", "https"}:
                scope["scheme"] = proto
        scope["client"] = (address, 0)
        return address

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        nonce = secrets.token_urlsafe(24)
        scope.setdefault("state", {})["csp_nonce"] = nonce
        headers = Headers(scope=scope)
        client = self.apply_proxy_headers(scope, headers)
        # Die explizite Außenadresse ist für ihren eigenen Host maßgeblich.
        # Kein Vertrauen in beliebige Forwarding-Header und kein HTTPS-Downgrade.
        if configured_public_scheme(headers.get("host", "")) == "https":
            scope["scheme"] = "https"

        async def deliver(message):
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                csrf = scope["state"].get("admin_csrf_cookie")
                if csrf:
                    carrier = Response()
                    issue_csrf_token(Request(scope), carrier, csrf)
                    for name, value in carrier.raw_headers:
                        if name == b"set-cookie":
                            response_headers.append("set-cookie", value.decode("latin-1"))
                response_headers["X-Content-Type-Options"] = "nosniff"
                response_headers["X-Frame-Options"] = "DENY"
                response_headers["Referrer-Policy"] = "no-referrer"
                response_headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
                response_headers["Content-Security-Policy"] = (
                    "default-src 'self'; img-src 'self' blob:; style-src 'self' 'unsafe-inline'; "
                    f"script-src 'self' 'nonce-{nonce}'; object-src 'none'; base-uri 'none'; "
                    "frame-ancestors 'none'; form-action 'self'"
                )
                # FastAPIs generierte Entwickler-UIs laden ihre gebündelten Bibliotheken
                # von diesen CDNs und enthalten eigenes Inline-Bootstrap-JavaScript.
                if scope["path"] in {"/docs", "/redoc", "/docs/oauth2-redirect"}:
                    response_headers["Content-Security-Policy"] = (
                        "default-src 'self'; img-src 'self' data: https://fastapi.tiangolo.com; "
                        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
                        "font-src 'self' https://fonts.gstatic.com; "
                        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.redoc.ly; "
                        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
                    )
                response_headers["Cache-Control"] = (
                    "no-cache" if scope["path"].startswith("/static/") else "private, no-store"
                )
                if scope["scheme"] == "https":
                    response_headers["Strict-Transport-Security"] = "max-age=31536000"
            await send(message)

        suppressed = False

        async def secure_send(message):
            nonlocal suppressed
            if suppressed:
                return
            session_hash = scope["state"].get("reader_session_hash")
            if (
                message["type"] == "http.response.start"
                and 200 <= message["status"] < 300
                and session_hash
            ):
                try:
                    renewed = await run_in_threadpool(renew_reader_session, session_hash)
                except (sqlite3.Error, HTTPException):
                    suppressed = True
                    await public_failure(
                        Request(scope), "Leseberechtigung derzeit nicht verfügbar.", 503
                    )(scope, receive, deliver)
                    return
                if renewed is None:
                    suppressed = True
                    await public_failure(
                        Request(scope),
                        "Leseberechtigung abgelaufen oder widerrufen. Bitte aktuellen QR-Code scannen.",
                        403,
                    )(scope, receive, deliver)
                    return
                now, expires_at = renewed
                request = Request(scope)
                carrier = Response()
                set_reader_cookie(carrier, request, request.cookies[READER_COOKIE], now, expires_at)
                cookie_headers = MutableHeaders(scope=message)
                for name, value in carrier.raw_headers:
                    if name == b"set-cookie":
                        cookie_headers.append("set-cookie", value.decode("latin-1"))
            await deliver(message)

        async def reject(code: int, message: str, retry: int = 0):
            extra = {"Retry-After": str(retry)} if retry else None
            await public_failure(Request(scope), message, code, headers=extra)(
                scope, receive, secure_send
            )

        if scope["method"] in {"POST", "PUT", "PATCH", "DELETE"}:
            length = headers.get("content-length")
            if length is not None:
                if len(length) > 20 or not length.isascii() or not length.isdecimal():
                    await reject(400, "Ungültige Request-Länge.")
                    return
                if int(length) > MAX_REQUEST_SIZE_BYTES:
                    await reject(413, "Die Anfrage ist zu groß.")
                    return
            if scope["method"] == "POST" and (
                scope["path"].rstrip("/") == "/hilfe" or PUBLIC_SUBMISSION.fullmatch(scope["path"])
            ):
                try:
                    retry = await run_in_threadpool(consume_rate_limit, client)
                except sqlite3.Error:
                    await reject(503, "Dienst vorübergehend nicht verfügbar.", 5)
                    return
                if retry:
                    await reject(
                        429, "Zu viele Übermittlungen. Bitte später erneut versuchen.", retry
                    )
                    return
            # Vollständig begrenzt einlesen, bevor Starlette temporäre Multipart-Dateien anlegt.
            chunks = []
            size = 0

            async def read_body():
                nonlocal size
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return False
                    chunk = message.get("body", b"")
                    size += len(chunk)
                    if size > MAX_REQUEST_SIZE_BYTES:
                        return False
                    chunks.append(chunk)
                    if not message.get("more_body", False):
                        return True

            try:
                complete = await asyncio.wait_for(read_body(), REQUEST_BODY_TIMEOUT_SECONDS)
            except TimeoutError:
                await reject(408, "Zeitlimit beim Übertragen der Anfrage überschritten.")
                return
            if not complete:
                await reject(
                    413 if size > MAX_REQUEST_SIZE_BYTES else 400,
                    "Unvollständige oder zu große Anfrage.",
                )
                return
            if length is not None and size != int(length):
                await reject(400, "Ungültige Request-Länge.")
                return
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
                return await receive()

            await self.app(scope, replay, secure_send)
        else:
            await self.app(scope, receive, secure_send)
