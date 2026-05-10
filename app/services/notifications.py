"""Optionale SMTP-Benachrichtigungen."""

import os
import smtplib
from email.message import EmailMessage

from app.templating import datetime_de


def env_flag(name: str, default: bool = False) -> bool:
    """Liest eine boolesche Environment-Variable."""

    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def notification_enabled() -> bool:
    """Prüft, ob die minimal nötigen SMTP-Variablen gesetzt sind."""

    return all(
        [
            os.environ.get("SMTP_HOST"),
            os.environ.get("SMTP_TO"),
            os.environ.get("SMTP_FROM"),
        ]
    )


def send_usage_notification(
    *,
    room_name: str,
    person_name: str,
    house: str,
    condition: str,
    remark: str,
    started_at: str,
    image_count: int,
) -> None:
    """Sendet optional eine E-Mail-Benachrichtigung für einen neuen Eintrag."""

    if not notification_enabled():
        return

    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    smtp_to = os.environ["SMTP_TO"]
    smtp_from = os.environ["SMTP_FROM"]
    smtp_starttls = env_flag("SMTP_STARTTLS", True)
    smtp_ssl = env_flag("SMTP_SSL", False)

    timestamp = datetime_de(started_at)
    remark_text = remark or "Keine Bemerkung"
    image_text = f"{image_count} Bild" if image_count == 1 else f"{image_count} Bilder"

    message = EmailMessage()
    message["Subject"] = f"Neuer Werkstatt-Eintrag: {condition}"
    message["From"] = smtp_from
    message["To"] = smtp_to
    message.set_content(
        "\n".join(
            [
                "Ein neuer Werkstatt-Eintrag wurde erstellt.",
                "",
                f"Raum: {room_name}",
                f"Name: {person_name}",
                f"Haus: {house}",
                f"Zustand: {condition}",
                f"Zeit: {timestamp}",
                f"Bilder: {image_text}",
                f"Bemerkung: {remark_text}",
            ]
        )
    )

    smtp_class = smtplib.SMTP_SSL if smtp_ssl else smtplib.SMTP
    with smtp_class(smtp_host, smtp_port, timeout=15) as smtp:
        if not smtp_ssl and smtp_starttls:
            smtp.starttls()
        if smtp_user:
            smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)
