"""Upload-Validierung."""

from fastapi import UploadFile


def allowed_image(upload: UploadFile) -> bool:
    """
    Prüft grob, ob ein Upload ein erlaubter Bildtyp ist.

    Achtung: upload.content_type kommt vom Client und ist daher keine harte
    Sicherheitsgarantie.
    """

    return upload.content_type in {"image/jpeg", "image/png", "image/webp"}
