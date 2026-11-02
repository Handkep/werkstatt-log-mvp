"""Fehlerseiten für Bewohner; Daten- und Download-Endpunkte bleiben unverändert."""

import re

from fastapi import Request
from fastapi.responses import PlainTextResponse

from app.templating import page_context, templates

DOCUMENT_PATH = re.compile(r"^/(?:|logbuch|hilfe|thanks|datenschutz|r/[^/]+(?:/submit)?)$")
ERROR_TITLES = {
    400: "Bitte prüfe deine Anfrage",
    403: "Zugang erforderlich",
    404: "Seite nicht gefunden",
    408: "Übertragung hat zu lange gedauert",
    413: "Die Anfrage ist zu groß",
    422: "Bitte prüfe deine Eingaben",
    429: "Bitte warte einen Moment",
    503: "Der Dienst ist gerade nicht verfügbar",
}


def wants_public_html(request: Request) -> bool:
    return bool(
        DOCUMENT_PATH.fullmatch(request.url.path)
        and "text/html" in request.headers.get("accept", "").lower()
    )


def public_failure(request: Request, message: str, status_code: int, headers=None):
    if not wants_public_html(request):
        return PlainTextResponse(message, status_code=status_code, headers=headers)
    room_path = re.fullmatch(r"(/r/[^/]+)/submit", request.url.path)
    return templates.TemplateResponse(
        request=request,
        name="public_error.html",
        context=page_context(
            request,
            "public",
            "logbook"
            if request.url.path == "/logbuch"
            else "help"
            if request.url.path == "/hilfe"
            else "rooms",
            error_title=ERROR_TITLES.get(status_code, "Etwas ist schiefgegangen"),
            error_message=message,
            error_code=status_code,
            return_url=room_path[1]
            if room_path
            else "/hilfe"
            if request.url.path == "/hilfe"
            else "/",
            retry_after=(headers or {}).get("Retry-After", ""),
        ),
        status_code=status_code,
        headers=headers,
    )
