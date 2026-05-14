"""Upload-Validierung."""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import MAX_UPLOAD_IMAGES, MAX_UPLOAD_SIZE_BYTES, MAX_UPLOAD_SIZE_MB


ALLOWED_IMAGE_FORMATS = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
    "WEBP": ("image/webp", ".webp"),
}


class UploadValidationError(ValueError):
    """Nutzerfreundlicher Fehler bei ungültigen Uploads."""


@dataclass(frozen=True)
class ValidatedImageUpload:
    """Ein vollständig geprüfter Bild-Upload vor dem Speichern."""

    filename: str
    original_filename: str
    content_type: str
    data: bytes


async def validate_image_uploads(uploads: list[UploadFile]) -> list[ValidatedImageUpload]:
    """Prüft Uploads vollständig und gibt speicherfertige Bilddaten zurück."""

    selected_uploads = [upload for upload in uploads if upload.filename]
    if len(selected_uploads) > MAX_UPLOAD_IMAGES:
        raise UploadValidationError(
            f"Bitte lade maximal {MAX_UPLOAD_IMAGES} Bilder hoch."
        )

    validated_uploads = []
    for upload in selected_uploads:
        original_filename = Path(upload.filename or "bild").name
        upload.file.seek(0)
        data = upload.file.read(MAX_UPLOAD_SIZE_BYTES + 1)

        if len(data) > MAX_UPLOAD_SIZE_BYTES:
            raise UploadValidationError(
                f"'{original_filename}' ist zu groß. Ein Bild darf maximal "
                f"{MAX_UPLOAD_SIZE_MB} MB groß sein."
            )

        image_format = detect_image_format(data, original_filename)
        content_type, suffix = ALLOWED_IMAGE_FORMATS[image_format]
        validated_uploads.append(
            ValidatedImageUpload(
                filename=f"{uuid4().hex}{suffix}",
                original_filename=original_filename,
                content_type=content_type,
                data=data,
            )
        )

    return validated_uploads


def detect_image_format(data: bytes, original_filename: str) -> str:
    """Erkennt und verifiziert das echte Bildformat."""

    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
            image_format = image.format
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise UploadValidationError(
            f"'{original_filename}' ist keine gültige Bilddatei."
        ) from exc

    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise UploadValidationError(
            f"'{original_filename}' hat ein nicht erlaubtes Bildformat. "
            "Erlaubt sind JPEG, PNG und WebP."
        )

    return image_format
