"""Öffentliche Seiten und Formulare."""

import json
import shutil
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse

from app.config import UPLOAD_DIR, logger
from app.constants import HOUSE_GROUPS, WORKSHOP_CONDITIONS
from app.db import db_connect, fetch_booking_entries, fetch_general_notes, load_active_rooms, load_room_by_slug
from app.forms import read_extra_field_values
from app.services.notifications import send_usage_notification
from app.services.pdf import build_room_qr_pdf
from app.services.uploads import allowed_image
from app.templating import page_context, random_name_placeholder, templates
from app.utils import now_iso, public_room_url, safe_download_slug

router = APIRouter()


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
        ),
    )


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

    if not person_name:
        return HTMLResponse("Name fehlt", status_code=400)

    if house_group not in HOUSE_GROUPS or not house_number.isdigit():
        return HTMLResponse("Haus ungültig", status_code=400)

    if condition not in WORKSHOP_CONDITIONS:
        return HTMLResponse("Zustand ungültig", status_code=400)

    with db_connect() as conn:
        room = load_room_by_slug(conn, room_slug)
        if room is None:
            return HTMLResponse("Raum nicht gefunden", status_code=404)

        try:
            extra_field_values = read_extra_field_values(room, form_data)
        except ValueError as exc:
            return HTMLResponse(str(exc), status_code=400)

        started_at = now_iso()
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
        image_count = 0

        for upload in images:
            if not upload.filename:
                continue
            if not allowed_image(upload):
                continue

            suffix = Path(upload.filename).suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
                suffix = ".img"

            filename = f"{uuid4().hex}{suffix}"
            target = UPLOAD_DIR / filename

            with target.open("wb") as file_obj:
                shutil.copyfileobj(upload.file, file_obj)

            conn.execute(
                """
                INSERT INTO usage_images
                (session_id, filename, original_filename, content_type, uploaded_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, filename, upload.filename, upload.content_type, now_iso()),
            )
            image_count += 1

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

    return RedirectResponse(f"/thanks?raum={room_slug}", status_code=303)


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
        page_context(request, "public", "rooms", room=room),
    )


@router.get("/anmerkungen", response_class=HTMLResponse)
def notes(request: Request):
    """Zeigt die letzten allgemeinen Anmerkungen an."""

    with db_connect() as conn:
        entries = fetch_general_notes(conn, limit=20)

    return templates.TemplateResponse(
        "notes.html",
        page_context(
            request,
            "public",
            "notes",
            entries=entries,
            saved=request.query_params.get("gespeichert") == "1",
            name_placeholder=random_name_placeholder(),
        ),
    )


@router.post("/anmerkungen")
def submit_note(person_name: str = Form(""), note: str = Form(...)):
    """Speichert eine allgemeine Anmerkung."""

    person_name = person_name.strip()
    note = note.strip()

    if not note:
        return HTMLResponse("Anmerkung fehlt", status_code=400)

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

    room_url = public_room_url(request, room_slug)
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

    path = UPLOAD_DIR / filename
    if not path.exists():
        return HTMLResponse("Datei nicht gefunden", status_code=404)
    return FileResponse(path)
