"""Zentrale Pfade und Laufzeit-Konfiguration."""

import logging
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR.parent / "data"))
DB_PATH = DATA_DIR / "app.db"
UPLOAD_DIR = DATA_DIR / "uploads"
FONT_DIR = BASE_DIR / "static" / "fonts"

SITE_TITLE = "Zelter5 Raumlog"

logger = logging.getLogger("werkstatt_log")

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
