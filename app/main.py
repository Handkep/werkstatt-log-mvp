"""Zelter5 Raumlog – öffentliche Meldeformulare und geschützte Verwaltung."""

import mimetypes
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.capabilities import validate_capability_config
from app.config import ALLOWED_HOSTS, BASE_DIR, DATA_DIR, SITE_TITLE, UPLOAD_DIR, logger
from app.db import init_db
from app.middleware import RequestProtectionMiddleware
from app.routes.admin import router as admin_router
from app.routes.public import router as public_router
from app.utils import configured_public_base_url


@asynccontextmanager
async def lifespan(app: FastAPI):
    def initialize():
        configured_public_base_url()
        validate_capability_config()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        init_db()

    await run_in_threadpool(initialize)
    yield


app = FastAPI(title=SITE_TITLE, lifespan=lifespan)
# Slim-Images enthalten nicht zwingend die systemweite MIME-Typenliste.
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/ttf", ".ttf")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.exception_handler(sqlite3.Error)
async def database_error(request: Request, exc: sqlite3.Error):
    logger.error("Datenbankzugriff fehlgeschlagen (%s)", type(exc).__name__)
    return PlainTextResponse(
        "Dienst vorübergehend nicht verfügbar.",
        status_code=503,
        headers={"Cache-Control": "private, no-store", "Retry-After": "5"},
    )


app.include_router(public_router)
app.include_router(admin_router)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS, www_redirect=False)
app.add_middleware(RequestProtectionMiddleware)
