"""Admin-Seiten."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import (
    db_connect,
    fetch_booking_entries,
    fetch_session_detail,
    fetch_session_images,
    load_active_rooms,
    load_room_by_slug,
    soft_delete_session,
)
from app.templating import display_extra_fields, page_context, templates

router = APIRouter()


@router.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    """Admin-Übersicht der letzten nicht gelöschten Buchungen."""

    selected_room = request.query_params.get("raum", "").strip()

    with db_connect() as conn:
        rooms = load_active_rooms(conn)
        entries = fetch_booking_entries(conn, selected_room=selected_room, limit=100)

    return templates.TemplateResponse(
        "admin.html",
        page_context(
            request,
            "admin",
            "admin",
            entries=entries,
            rooms=rooms,
            selected_room=selected_room,
        ),
    )


@router.get("/admin/session/{session_id}", response_class=HTMLResponse)
def session_detail(request: Request, session_id: int):
    """Detailansicht eines einzelnen Nutzungs-Eintrags."""

    with db_connect() as conn:
        entry = fetch_session_detail(conn, session_id)
        images = fetch_session_images(conn, session_id)

    if entry is None:
        return HTMLResponse("Eintrag nicht gefunden", status_code=404)

    with db_connect() as conn:
        room = load_room_by_slug(conn, entry["room_slug"])

    entry = dict(entry)
    extra_fields = display_extra_fields(room, entry.get("extra_fields_json")) if room else []

    return templates.TemplateResponse(
        "session_detail.html",
        page_context(
            request,
            "admin",
            "admin",
            entry=entry,
            images=images,
            extra_fields=extra_fields,
        ),
    )


@router.post("/admin/session/{session_id}/delete")
def delete_session(session_id: int):
    """Markiert einen Nutzungs-Eintrag als gelöscht."""

    with db_connect() as conn:
        deleted = soft_delete_session(conn, session_id)

    if not deleted:
        return HTMLResponse("Eintrag nicht gefunden", status_code=404)

    return RedirectResponse("/admin", status_code=303)
