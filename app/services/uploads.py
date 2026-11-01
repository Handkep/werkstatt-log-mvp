"""Strenge Bildprüfung und metadatenfreie Neucodierung vor jeder Speicherung."""

import struct
import warnings
import zlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import (
    MAX_IMAGE_DIMENSION,
    MAX_IMAGE_PIXELS,
    MAX_UPLOAD_IMAGES,
    MAX_UPLOAD_SIZE_BYTES,
    MAX_UPLOAD_SIZE_MB,
)

ALLOWED_IMAGE_FORMATS = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
    "WEBP": ("image/webp", ".webp"),
}


class UploadValidationError(ValueError):
    """Nutzerfreundlicher Fehler bei ungültigen Uploads."""


@dataclass(frozen=True)
class ValidatedImageUpload:
    filename: str
    original_filename: str
    content_type: str
    data: bytes


def normalize_image(data: bytes) -> tuple[str, bytes]:
    """Prüft Struktur UND Pixel; übernimmt ausschließlich neue Pixel, keine Metadaten."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                image_format = image.format
                if image_format not in ALLOWED_IMAGE_FORMATS:
                    raise UploadValidationError("Erlaubt sind JPEG, PNG und WebP.")
                width, height = image.size
                if (
                    min(width, height) < 1
                    or max(width, height) > MAX_IMAGE_DIMENSION
                    or width * height > MAX_IMAGE_PIXELS
                ):
                    raise UploadValidationError(
                        "Das Bild hat zu große Abmessungen oder zu viele Pixel."
                    )
                if getattr(image, "n_frames", 1) != 1:
                    raise UploadValidationError(
                        "Bitte nur einzelne, nicht animierte Bilder hochladen."
                    )
                if image_format == "JPEG" and not data.endswith(b"\xff\xd9"):
                    raise UploadValidationError("Die JPEG-Datei ist unvollständig.")
                if image_format == "PNG" and not data.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82"):
                    raise UploadValidationError("Die PNG-Datei ist unvollständig.")
                image.verify()
            with Image.open(BytesIO(data)) as image:
                image.load()
                with ImageOps.exif_transpose(image) as oriented:
                    mode = "RGB" if image_format == "JPEG" else "RGBA"
                    with oriented.convert(mode) as converted:
                        with Image.new(mode, converted.size) as clean:
                            clean.paste(converted)
                            output = BytesIO()
                            clean.save(output, format=image_format)
                            normalized = output.getvalue()
                if len(normalized) > MAX_UPLOAD_SIZE_BYTES:
                    raise UploadValidationError(
                        "Das neu codierte Bild überschreitet das Dateilimit."
                    )
                return image_format, normalized
    except UploadValidationError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        EOFError,
        TypeError,
        OverflowError,
        struct.error,
        zlib.error,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise UploadValidationError("Die Bilddatei ist beschädigt oder ungültig.") from exc


def validate_image_uploads(uploads: list[UploadFile]) -> list[ValidatedImageUpload]:
    """Synchron im Worker-Thread aufrufen, nie im Async-Event-Loop."""
    selected = [upload for upload in uploads if upload.filename]
    if len(selected) > MAX_UPLOAD_IMAGES:
        raise UploadValidationError(f"Bitte lade maximal {MAX_UPLOAD_IMAGES} Bilder hoch.")
    validated = []
    for upload in selected:
        upload.file.seek(0)
        data = upload.file.read(MAX_UPLOAD_SIZE_BYTES + 1)
        if len(data) > MAX_UPLOAD_SIZE_BYTES:
            raise UploadValidationError(f"Ein Bild darf maximal {MAX_UPLOAD_SIZE_MB} MB groß sein.")
        image_format, data = normalize_image(data)
        content_type, suffix = ALLOWED_IMAGE_FORMATS[image_format]
        validated.append(
            ValidatedImageUpload(
                filename=f"{uuid4().hex}{suffix}",
                original_filename=Path(upload.filename or "Bild").name[:255],
                content_type=content_type,
                data=data,
            )
        )
    return validated
