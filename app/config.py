"""Zentrale Pfade und Laufzeit-Konfiguration."""

import logging
import os
from pathlib import Path

logger = logging.getLogger("werkstatt_log")


def positive_int_env(name: str, default: int) -> int:
    """Liest eine positive Ganzzahl aus der Umgebung oder nutzt den Default."""

    raw_value = os.environ.get(name)
    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError:
        logger.warning("%s=%r ist ungültig, verwende Default %s", name, raw_value, default)
        return default

    if value <= 0:
        logger.warning("%s=%r ist nicht positiv, verwende Default %s", name, raw_value, default)
        return default

    return value


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR.parent / "data"))
DB_PATH = DATA_DIR / "app.db"
UPLOAD_DIR = DATA_DIR / "uploads"
FONT_DIR = BASE_DIR / "static" / "fonts"

SITE_TITLE = "Zelter5 Raumlog"

MAX_UPLOAD_IMAGES = positive_int_env("MAX_UPLOAD_IMAGES", 5)
MAX_UPLOAD_SIZE_MB = positive_int_env("MAX_UPLOAD_SIZE_MB", 5)
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
MAX_NAME_LENGTH = positive_int_env("MAX_NAME_LENGTH", 100)
MAX_HOUSE_LENGTH = positive_int_env("MAX_HOUSE_LENGTH", 10)
MAX_COMMENT_LENGTH = positive_int_env("MAX_COMMENT_LENGTH", 2000)
MAX_GENERAL_NOTE_LENGTH = positive_int_env("MAX_GENERAL_NOTE_LENGTH", 4000)

LIMITS = {
    "max_upload_images": MAX_UPLOAD_IMAGES,
    "max_upload_size_mb": MAX_UPLOAD_SIZE_MB,
    "max_name_length": MAX_NAME_LENGTH,
    "max_house_length": MAX_HOUSE_LENGTH,
    "max_comment_length": MAX_COMMENT_LENGTH,
    "max_general_note_length": MAX_GENERAL_NOTE_LENGTH,
}

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
