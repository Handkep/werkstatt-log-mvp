"""Admin-Seiten."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import csrf_token_for_request, issue_csrf_token, require_admin, require_admin_csrf
from app.capabilities import room_qr_url, rotate_all_reader_access
from app.constants import WORKSHOP_CONDITIONS
from app.db import (
    db_connect,
    fetch_booking_entries,
    fetch_general_notes,
    fetch_session_detail,
    fetch_session_images,
    load_active_rooms,
    load_room_by_slug,
    soft_delete_session,
)
from app.routes.public import latest_room_status, logbook, room_bookings_response, uploaded_file
from app.services.pdf import room_qr_pdf_response
from app.templating import display_extra_fields, page_context, templates

router = APIRouter(dependencies=[Depends(require_admin), Depends(require_admin_csrf)])


@router.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    """Admin-Übersicht der letzten nicht gelöschten Buchungen."""

    selected_room = request.query_params.get("raum", "").strip()
    selected_condition = request.query_params.get("zustand", "").strip()
    search = request.query_params.get("q", "").strip()
    if selected_condition not in WORKSHOP_CONDITIONS:
        selected_condition = ""

    with db_connect() as conn:
        rooms = load_active_rooms(conn)
        entries = fetch_booking_entries(
            conn,
            selected_room=selected_room,
            selected_condition=selected_condition,
            search=search,
            limit=100,
        )

    problem_count = sum(1 for entry in entries if entry["condition"] == "Problem/Defekt")

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context=page_context(
            request,
            "admin",
            "admin",
            entries=entries,
            rooms=rooms,
            conditions=WORKSHOP_CONDITIONS,
            selected_room=selected_room,
            selected_condition=selected_condition,
            search=search,
            problem_count=problem_count,
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

    csrf_token = csrf_token_for_request(request)
    response = templates.TemplateResponse(
        request=request,
        name="session_detail.html",
        context=page_context(
            request,
            "admin",
            "admin",
            csrf_token=csrf_token,
            entry=entry,
            images=images,
            extra_fields=extra_fields,
        ),
    )

    issue_csrf_token(request, response, csrf_token)
    return response


@router.get("/admin/nachrichten", response_class=HTMLResponse)
def admin_messages(request: Request):
    """Eingereichte Nachrichten sind ausschließlich für Admins sichtbar."""
    with db_connect() as conn:
        entries = fetch_general_notes(conn)
    return templates.TemplateResponse(
        request=request,
        name="admin_messages.html",
        context=page_context(request, "admin", "admin_messages", entries=entries),
    )


@router.post("/admin/session/{session_id}/delete")
def delete_session(session_id: int):
    """Markiert einen Nutzungs-Eintrag als gelöscht."""

    with db_connect() as conn:
        deleted = soft_delete_session(conn, session_id)

    if not deleted:
        return HTMLResponse("Eintrag nicht gefunden", status_code=404)

    return RedirectResponse("/admin", status_code=303)


@router.get("/admin/raumzugaenge", response_class=HTMLResponse)
def room_access_management(request: Request):
    with db_connect() as conn:
        rooms = load_active_rooms(conn)
    token = csrf_token_for_request(request)
    response = templates.TemplateResponse(
        request=request,
        name="room_access_admin.html",
        context=page_context(request, "admin", "room_access", rooms=rooms, csrf_token=token),
    )
    issue_csrf_token(request, response, token)
    return response


@router.post("/admin/reader-access/rotate")
def rotate_global_reader_access():
    with db_connect() as conn:
        rotate_all_reader_access(conn)
    return RedirectResponse("/admin/raumzugaenge?erneuert=1", status_code=303)


def active_admin_room(room_id: int) -> dict | None:
    with db_connect() as conn:
        return next((room for room in load_active_rooms(conn) if room["id"] == room_id), None)


@router.get("/admin/rooms/{room_id}/qr.pdf")
def admin_room_qr_pdf(room_id: int):
    room = active_admin_room(room_id)
    if room is None:
        return HTMLResponse("Raum nicht gefunden", status_code=404)
    return room_qr_pdf_response(room)


@router.post("/admin/rooms/{room_id}/access-link")
def admin_copy_access_link(room_id: int):
    room = active_admin_room(room_id)
    if room is None:
        return HTMLResponse("Raum nicht gefunden", status_code=404)
    return {"url": room_qr_url(room)}


@router.get("/admin/uploads/{filename}")
def admin_uploaded_file(filename: str):
    """Basic-Auth bleibt für Admin-Bilder im selben URL-Schutzbereich."""
    return uploaded_file(filename)


@router.get("/admin/logbuch", response_class=HTMLResponse)
def admin_logbook(request: Request):
    return logbook(request)


@router.get("/admin/rooms/latest-status")
def admin_latest_room_status():
    return latest_room_status()


@router.get("/admin/rooms/{room_id}/recent-bookings")
def admin_room_recent_bookings(request: Request, room_id: int):
    room = active_admin_room(room_id)
    if room is None:
        return HTMLResponse("Raum nicht gefunden", status_code=404)
    return room_bookings_response(request, room)
