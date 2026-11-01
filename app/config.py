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


# Unabhängige Grenzen für komprimierte Dateien, decodierte Bilder und Gesamtspeicher.
MAX_IMAGE_DIMENSION = positive_int_env("MAX_IMAGE_DIMENSION", 10000)
MAX_IMAGE_PIXELS = positive_int_env("MAX_IMAGE_PIXELS", 20_000_000)
MAX_UPLOAD_STORAGE_BYTES = positive_int_env("MAX_UPLOAD_STORAGE_MB", 1024) * 1024 * 1024
MAX_REQUEST_SIZE_BYTES = (
    positive_int_env("MAX_REQUEST_SIZE_MB", MAX_UPLOAD_IMAGES * MAX_UPLOAD_SIZE_MB + 1)
    * 1024
    * 1024
)
REQUEST_BODY_TIMEOUT_SECONDS = positive_int_env("REQUEST_BODY_TIMEOUT_SECONDS", 30)
RATE_LIMIT_COUNT = positive_int_env("RATE_LIMIT_COUNT", 10)
RATE_LIMIT_GLOBAL_COUNT = positive_int_env("RATE_LIMIT_GLOBAL_COUNT", 100)
RATE_LIMIT_WINDOW_SECONDS = positive_int_env("RATE_LIMIT_WINDOW_SECONDS", 600)
SQLITE_BUSY_TIMEOUT_MS = positive_int_env("SQLITE_BUSY_TIMEOUT_MS", 5000)
MAX_HOUSE_NUMBER_LENGTH = max(1, MAX_HOUSE_LENGTH - 2)
LIMITS["max_house_number_length"] = MAX_HOUSE_NUMBER_LENGTH
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
    if host.strip()
]
TRUSTED_PROXY_NETWORKS = [
    network.strip()
    for network in os.environ.get("TRUSTED_PROXIES", "").split(",")
    if network.strip()
]

READER_SESSION_SECONDS = positive_int_env("READER_SESSION_DAYS", 365) * 24 * 60 * 60
