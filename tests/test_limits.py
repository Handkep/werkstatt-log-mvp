import asyncio
import ipaddress
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app import db, middleware
from app.main import app
from tests.conftest import VALID


def test_request_size_and_rate_limit_before_parsing(client, monkeypatch):
    monkeypatch.setattr(middleware, "MAX_REQUEST_SIZE_BYTES", 10)
    response = client.post("/hilfe", content=b"x" * 11)
    assert response.status_code == 413
    with db.db_connect() as conn:
        assert conn.execute("SELECT count(*) FROM rate_limits").fetchone()[0] == 0


def test_rate_limit_shared_by_endpoints_and_clients(client, monkeypatch):
    monkeypatch.setattr(middleware, "RATE_LIMIT_COUNT", 2)
    assert client.post("/hilfe", data={"note": "one"}, follow_redirects=False).status_code == 303
    assert client.post("/r/werkstatt/submit", data=VALID, follow_redirects=False).status_code == 303
    response = client.post("/hilfe", data={"note": "three"}, headers={"X-Forwarded-For": "1.2.3.4"})
    assert response.status_code == 429
    assert 1 <= int(response.headers["retry-after"]) <= 600
    with TestClient(
        app, base_url="https://testserver", headers={"Origin": "https://testserver"}
    ) as other:
        assert other.post("/hilfe", data={"note": "four"}).status_code == 429
    db.init_db()  # Neustart setzt Limit und Hash-Schlüssel nicht zurück.
    assert client.post("/hilfe", data={"note": "five"}).status_code == 429
    with db.db_connect() as conn:
        rows = conn.execute("SELECT bucket FROM rate_limits").fetchall()
        assert len(rows) == 2
        assert all("testclient" not in row[0] and "1.2.3.4" not in row[0] for row in rows)


def test_rate_limits_atomic_concurrent_and_global(client, monkeypatch):
    monkeypatch.setattr(middleware, "RATE_LIMIT_COUNT", 3)
    monkeypatch.setattr(middleware, "RATE_LIMIT_GLOBAL_COUNT", 5)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(middleware.consume_rate_limit, ["same-address"] * 16))
    assert results.count(0) == 3
    assert middleware.consume_rate_limit("new-address-1") == 0
    assert middleware.consume_rate_limit("new-address-2") == 0
    assert middleware.consume_rate_limit("new-address-3") > 0


def test_rate_window_expires(client, monkeypatch):
    monkeypatch.setattr(middleware, "RATE_LIMIT_COUNT", 1)
    now = int(middleware.time.time())
    assert middleware.consume_rate_limit("client") == 0
    assert middleware.consume_rate_limit("client") > 0
    monkeypatch.setattr(middleware.time, "time", lambda: now + 601)
    assert middleware.consume_rate_limit("client") == 0


def test_proxy_headers_only_from_trusted_proxies():
    protection = middleware.RequestProtectionMiddleware(None)
    protection.trusted_proxies = [ipaddress.ip_network("10.0.0.0/24")]

    def resolve(peer, chain, proto="https"):
        scope = {"client": (peer, 4321), "scheme": "http"}
        headers = middleware.Headers({"x-forwarded-for": chain, "x-forwarded-proto": proto})
        return protection.apply_proxy_headers(scope, headers), scope["scheme"]

    assert resolve("1.2.3.4", "8.8.8.8") == ("1.2.3.4", "http")
    assert resolve("10.0.0.1", "6.6.6.6, 1.2.3.4, 10.0.0.2") == ("1.2.3.4", "https")
    assert resolve("10.0.0.1", "invalid", "evil") == ("10.0.0.1", "http")


def test_chunked_body_limits_and_timeout_without_parser(monkeypatch):
    called = []

    async def downstream(scope, receive, send):
        called.append(True)

    protection = middleware.RequestProtectionMiddleware(downstream)
    monkeypatch.setattr(middleware, "MAX_REQUEST_SIZE_BYTES", 5)

    async def execute(parts, headers=(), pause=False):
        messages = []
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/admin/action",
            "scheme": "http",
            "headers": headers,
            "client": ("1.2.3.4", 1),
        }

        async def receive():
            if pause:
                await asyncio.sleep(0.05)
            return parts.pop(0)

        async def send(message):
            messages.append(message)

        await protection(scope, receive, send)
        return messages[0]["status"]

    assert (
        asyncio.run(
            execute(
                [
                    {"type": "http.request", "body": b"123", "more_body": True},
                    {"type": "http.request", "body": b"456", "more_body": False},
                ]
            )
        )
        == 413
    )
    assert asyncio.run(execute([], headers=[(b"content-length", b"-1")])) == 400
    assert (
        asyncio.run(
            execute([{"type": "http.request", "body": b"1"}], headers=[(b"content-length", b"2")])
        )
        == 400
    )
    monkeypatch.setattr(middleware, "REQUEST_BODY_TIMEOUT_SECONDS", 0.01)
    assert asyncio.run(execute([{"type": "http.request", "body": b"1"}], pause=True)) == 408
    assert called == []


def test_rate_limit_database_failure_is_closed(client, monkeypatch):
    import sqlite3

    def fail(client):
        raise sqlite3.OperationalError("private SQL error")

    monkeypatch.setattr(middleware, "consume_rate_limit", fail)
    response = client.post("/hilfe", data={"note": "test"})
    assert response.status_code == 503
    assert "private SQL" not in response.text
    assert response.headers["retry-after"] == "5"
