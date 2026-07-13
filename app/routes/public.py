"""Öffentliche Seiten und Formulare."""

import json
import re
from io import BytesIO

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse

from app.config import (
    MAX_COMMENT_LENGTH,
    MAX_GENERAL_NOTE_LENGTH,
    MAX_HOUSE_LENGTH,
    MAX_NAME_LENGTH,
    UPLOAD_DIR,
    logger,
)
from app.constants import HOUSE_GROUPS, WORKSHOP_CONDITIONS
from app.db import (
    db_connect,
    fetch_booking_entries,
    fetch_general_notes,
    fetch_image_by_filename,
    load_active_rooms,
    load_room_by_slug,
)
from app.forms import read_extra_field_values
from app.services.notifications import send_usage_notification
from app.services.pdf import build_room_qr_pdf
from app.services.uploads import UploadValidationError, validate_image_uploads
from app.templating import page_context, random_name_placeholder, templates
from app.utils import now_iso, public_room_url, safe_download_slug

router = APIRouter()
UPLOAD_FILENAME_PATTERN = re.compile(r"^[0-9a-f]{32}\.(jpg|jpeg|png|webp|img)$")


def is_room_mode(request: Request) -> bool:
    """Prüft, ob die aktuelle öffentliche Seite im QR-Raummodus läuft."""

    return request.query_params.get("mode") == "room"


def length_error(label: str, max_length: int) -> str:
    """Erzeugt eine verständliche Fehlermeldung für zu lange Eingaben."""

    return f"{label} darf maximal {max_length} Zeichen lang sein."


def room_form_response(
    request: Request,
    room: dict,
    *,
    error: str = "",
    form_values: dict | None = None,
) -> HTMLResponse:
    """Rendert das Raumformular mit optionaler Fehlermeldung."""

    return templates.TemplateResponse(
        "room_form.html",
        page_context(
            request,
            "public",
            "rooms",
            room=room,
            house_groups=HOUSE_GROUPS,
            conditions=WORKSHOP_CONDITIONS,
            name_placeholder=random_name_placeholder(),
            form_error=error,
            form_values=form_values or {},
            room_mode=is_room_mode(request),
        ),
        status_code=400 if error else 200,
    )


def notes_response(
    request: Request,
    *,
    error: str = "",
    form_values: dict | None = None,
    saved: bool = False,
) -> HTMLResponse:
    """Rendert das Anmerkungsformular mit Einträgen und optionalem Fehler."""

    with db_connect() as conn:
        entries = fetch_general_notes(conn, limit=20)

    return templates.TemplateResponse(
        "notes.html",
        page_context(
            request,
            "public",
            "notes",
            entries=entries,
            saved=saved,
            name_placeholder=random_name_placeholder(),
            form_error=error,
            form_values=form_values or {},
        ),
        status_code=400 if error else 200,
    )


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    """Startseite: zeigt alle aktiven Räume als Auswahl an."""

    with db_connect() as conn:
        rooms = load_active_rooms(conn)

    return templates.TemplateResponse(
        "room_index.html",
        page_context(request, "public", "rooms", rooms=rooms),
    )


@router.get("/r/{room_slug}", response_class=HTMLResponse)
def room_form(request: Request, room_slug: str):
    """Formularseite für einen bestimmten Raum."""

    with db_connect() as conn:
        room = load_room_by_slug(conn, room_slug)

    if room is None:
        return HTMLResponse("Raum nicht gefunden", status_code=404)

    return room_form_response(request, room)


@router.post("/r/{room_slug}/submit")
async def submit_usage(
    request: Request,
    room_slug: str,
    person_name: str = Form(...),
    house_group: str = Form(...),
    house_number: str = Form(...),
    condition: str = Form(...),
    remark: str = Form(""),
    images: list[UploadFile] = File(default=[]),
):
    """Verarbeitet das Nutzungsformular eines Raums."""

    form_data = await request.form()

    person_name = person_name.strip()
    house_group = house_group.strip().upper()
    house_number = house_number.strip()
    house = f"{house_group}{house_number}"
    condition = condition.strip()
    remark = remark.strip()

    with db_connect() as conn:
        room = load_room_by_slug(conn, room_slug)
    if room is None:
        return HTMLResponse("Raum nicht gefunden", status_code=404)

    form_values = {
        "person_name": person_name,
        "house_group": house_group,
        "house_number": house_number,
        "condition": condition,
        "remark": remark,
    }
    for field in room.get("extra_fields", []):
        field_name = field.get("name", "").strip()
        if field_name:
            raw_value = form_data.get(field_name, "")
            form_values[field_name] = raw_value.strip() if isinstance(raw_value, str) else ""

    if not person_name:
        return room_form_response(request, room, error="Name fehlt", form_values=form_values)
    if len(person_name) > MAX_NAME_LENGTH:
        return room_form_response(
            request,
            room,
            error=length_error("Name", MAX_NAME_LENGTH),
            form_values=form_values,
        )

    if house_group not in HOUSE_GROUPS or not house_number.isdigit():
        return room_form_response(request, room, error="Haus ungültig", form_values=form_values)

    if len(house) > MAX_HOUSE_LENGTH:
        return room_form_response(
            request,
            room,
            error=length_error("Haus", MAX_HOUSE_LENGTH),
            form_values=form_values,
        )

    if condition not in WORKSHOP_CONDITIONS:
        return room_form_response(request, room, error="Zustand ungültig", form_values=form_values)

    if len(remark) > MAX_COMMENT_LENGTH:
        return room_form_response(
            request,
            room,
            error=length_error("Bemerkung", MAX_COMMENT_LENGTH),
            form_values=form_values,
        )

    try:
        extra_field_values = read_extra_field_values(room, form_data)
    except ValueError as exc:
        return room_form_response(request, room, error=str(exc), form_values=form_values)

    try:
        validated_images = await validate_image_uploads(images)
    except UploadValidationError as exc:
        return room_form_response(request, room, error=str(exc), form_values=form_values)

    started_at = now_iso()
    saved_paths = []
    try:
        with db_connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO usage_sessions (room_id, person_name, house, condition, remark, extra_fields_json, started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    room["id"],
                    person_name,
                    house,
                    condition,
                    remark,
                    json.dumps(extra_field_values, ensure_ascii=False) if extra_field_values else None,
                    started_at,
                ),
            )
            session_id = cur.lastrowid

            for image in validated_images:
                target = UPLOAD_DIR / image.filename
                target.write_bytes(image.data)
                saved_paths.append(target)

                conn.execute(
                    """
                    INSERT INTO usage_images
                    (session_id, filename, original_filename, content_type, uploaded_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        image.filename,
                        image.original_filename,
                        image.content_type,
                        now_iso(),
                    ),
                )
    except Exception:
        for path in saved_paths:
            path.unlink(missing_ok=True)
        raise

    image_count = len(validated_images)

    try:
        send_usage_notification(
            room_name=room["name"],
            person_name=person_name,
            house=house,
            condition=condition,
            remark=remark,
            started_at=started_at,
            image_count=image_count,
        )
    except Exception:
        logger.exception("Konnte Benachrichtigungs-E-Mail nicht senden")

    thanks_url = f"/thanks?raum={room_slug}"
    if is_room_mode(request):
        thanks_url += "&mode=room"
    return RedirectResponse(thanks_url, status_code=303)


@router.get("/thanks", response_class=HTMLResponse)
def thanks(request: Request):
    """Dankesseite nach erfolgreichem Eintrag."""

    room_slug = request.query_params.get("raum", "")

    with db_connect() as conn:
        room = load_room_by_slug(conn, room_slug) if room_slug else None
        if room is None:
            rooms = load_active_rooms(conn)
            room = rooms[0] if rooms else None

    return templates.TemplateResponse(
        "thanks.html",
        page_context(request, "public", "rooms", room=room, room_mode=is_room_mode(request)),
    )


@router.get("/anmerkungen", response_class=HTMLResponse)
def notes(request: Request):
    """Zeigt die letzten allgemeinen Anmerkungen an."""

    return notes_response(request, saved=request.query_params.get("gespeichert") == "1")


@router.post("/anmerkungen")
def submit_note(request: Request, person_name: str = Form(""), note: str = Form(...)):
    """Speichert eine allgemeine Anmerkung."""

    person_name = person_name.strip()
    note = note.strip()

    form_values = {"person_name": person_name, "note": note}

    if not note:
        return notes_response(request, error="Anmerkung fehlt", form_values=form_values)
    if len(person_name) > MAX_NAME_LENGTH:
        return notes_response(
            request,
            error=length_error("Name", MAX_NAME_LENGTH),
            form_values=form_values,
        )
    if len(note) > MAX_GENERAL_NOTE_LENGTH:
        return notes_response(
            request,
            error=length_error("Nachricht", MAX_GENERAL_NOTE_LENGTH),
            form_values=form_values,
        )

    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO general_notes (person_name, note, created_at)
            VALUES (?, ?, ?)
            """,
            (person_name, note, now_iso()),
        )

    return RedirectResponse("/anmerkungen?gespeichert=1", status_code=303)


@router.get("/datenschutz", response_class=HTMLResponse)
def privacy(request: Request):
    """Datenschutzseite."""

    return templates.TemplateResponse("privacy.html", page_context(request, "meta", "privacy"))


@router.get("/letzte-buchungen", response_class=HTMLResponse)
def recent_bookings(request: Request):
    """Öffentliche Übersicht der letzten nicht gelöschten Buchungen."""

    selected_room = request.query_params.get("raum", "").strip()

    with db_connect() as conn:
        rooms = load_active_rooms(conn)
        entries = fetch_booking_entries(conn, selected_room=selected_room, limit=20)

    return templates.TemplateResponse(
        "recent_bookings.html",
        page_context(
            request,
            "public",
            "recent",
            entries=entries,
            rooms=rooms,
            selected_room=selected_room,
        ),
    )


@router.get("/r/{room_slug}/qr.pdf")
def room_qr_pdf(request: Request, room_slug: str):
    """Erstellt und liefert ein PDF mit QR-Code für einen bestimmten Raum."""

    with db_connect() as conn:
        room = load_room_by_slug(conn, room_slug)

    if room is None:
        return HTMLResponse("Raum nicht gefunden", status_code=404)

    room_url = public_room_url(request, room_slug, room_mode=True)
    pdf_bytes = build_room_qr_pdf(room, room_url)

    filename = f"zelter5-qr-{safe_download_slug(room_slug)}.pdf"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers=headers,
    )


@router.get("/uploads/{filename}")
def uploaded_file(filename: str):
    """Liefert hochgeladene Bilder aus."""

    if not UPLOAD_FILENAME_PATTERN.fullmatch(filename):
        return HTMLResponse("Datei nicht gefunden", status_code=404)

    with db_connect() as conn:
        image = fetch_image_by_filename(conn, filename)
    if image is None:
        return HTMLResponse("Datei nicht gefunden", status_code=404)

    path = UPLOAD_DIR / filename
    if not path.is_file():
        return HTMLResponse("Datei nicht gefunden", status_code=404)
    return FileResponse(path, media_type=image["content_type"] or "application/octet-stream")
