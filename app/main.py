"""
Zelter5 Raumlog
===============

Kleine FastAPI-Webanwendung zur Dokumentation der Nutzung gemeinsamer Räume
(z. B. Werkstatt, Dachterrasse, Sommerküche, Sauna, Ruheraum).
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR, SITE_TITLE
from app.db import init_db
from app.routes.admin import router as admin_router
from app.routes.public import router as public_router

app = FastAPI(title=SITE_TITLE)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("startup")
def on_startup() -> None:
    """Initialisiert die Datenbank beim Start der FastAPI-Anwendung."""

    init_db()


app.include_router(public_router)
app.include_router(admin_router)
