"""Öffentliche Seiten und Formulare."""

import json
import os
import re
import sqlite3
import tempfile
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData

from app.auth import csrf_token_for_request, issue_csrf_token, request_is_admin, require_same_origin
from app.capabilities import (
    exchange_room_token,
    has_reader_access,
    require_reader,
    room_qr_url,
)
from app.config import (
    MAX_COMMENT_LENGTH,
    MAX_GENERAL_NOTE_LENGTH,
    MAX_HOUSE_LENGTH,
    MAX_HOUSE_NUMBER_LENGTH,
    MAX_NAME_LENGTH,
    MAX_UPLOAD_STORAGE_BYTES,
    READER_SESSION_SECONDS,
    UPLOAD_DIR,
    logger,
)
from app.constants import HOUSE_GROUPS, WORKSHOP_CONDITIONS
from app.db import (
    db_connect,
    fetch_booking_entries,
    fetch_image_by_filename,
    fetch_latest_room_status,
    load_active_rooms,
    load_room_by_slug,
)
from app.forms import read_extra_field_values
from app.public_errors import public_failure
from app.services.notifications import notify_usage_safely
from app.services.pdf import room_qr_pdf_response
from app.services.uploads import UploadValidationError, validate_image_uploads
from app.templating import page_context, random_name_placeholder, templates
from app.utils import now_iso

router = APIRouter()
UPLOAD_FILENAME_PATTERN = re.compile(r"^[0-9a-f]{32}\.(jpg|jpeg|png|webp|img)$")


def length_error(label: str, max_length: int) -> str:
    """Erzeugt eine verständliche Fehlermeldung für zu lange Eingaben."""

    return f"{label} darf maximal {max_length} Zeichen lang sein."


def room_form_response(
    request: Request,
    room: dict,
    *,
    error: str = "",
    form_values: dict | None = None,
    error_field: str = "",
) -> HTMLResponse:
    """Rendert das Raumformular mit optionaler Fehlermeldung."""

    with db_connect() as conn:
        has_read_access = has_reader_access(conn, request)
    admin_csrf = csrf_token_for_request(request) if request_is_admin(request) else ""
    values = form_values or {}
    if error and not error_field:
        labels = {
            "Name": "person_name",
            "Haus": "house_number",
            "Zustand": "condition",
            "Bemerkung": "remark",
        }
        labels.update(
            {
                field.get("label", field["name"]): field["name"]
                for field in room.get("extra_fields", [])
                if field.get("name")
            }
        )
        error_field = next(
            (
                labels[label]
                for label in sorted(labels, key=len, reverse=True)
                if label and error.startswith(label)
            ),
            "images",
        )
        if error_field == "house_number" and values.get("house_group", "") not in HOUSE_GROUPS:
            error_field = "house_group"
    response = templates.TemplateResponse(
        request=request,
        name="room_form.html",
        context=page_context(
            request,
            "public",
            "rooms",
            room=room,
            house_groups=HOUSE_GROUPS,
            conditions=WORKSHOP_CONDITIONS,
            name_placeholder=random_name_placeholder(),
            form_error=error,
            field_errors={error_field: error} if error else {},
            form_values=form_values or {},
            has_read_access=has_read_access,
            csrf_token=admin_csrf,
            room_access_exchange_path=f"/r/{quote(room['slug'], safe='')}/access",
        ),
        status_code=400 if error else 200,
    )
    if admin_csrf:
        issue_csrf_token(request, response, admin_csrf)
    return response


def help_response(
    request: Request,
    *,
    error: str = "",
    form_values: dict | None = None,
    saved: bool = False,
    error_field: str = "",
) -> HTMLResponse:
    """Rendert Hilfe & Infos mit dem öffentlichen Nachrichtenformular."""

    return templates.TemplateResponse(
        request=request,
        name="help.html",
        context=page_context(
            request,
            "public",
            "help",
            saved=saved,
            name_placeholder=random_name_placeholder(),
            form_error=error,
            field_errors={
                (error_field or ("person_name" if error.startswith("Name") else "note")): error
            }
            if error
            else {},
            form_values=form_values or {},
        ),
        status_code=400 if error else 200,
    )


def invalid_form_response(request: Request, body, field: str):
    """FastAPI-Pflichtfeldfehler mit vorhandenen Textwerten im Formular anzeigen."""
    if not isinstance(body, FormData):
        return public_failure(request, "Bitte fülle alle Pflichtfelder korrekt aus.", 422)
    values = {key: value for key, value in body.items() if isinstance(value, str)}
    labels = {
        "person_name": "Name",
        "house_group": "Haus",
        "house_number": "Nummer",
        "condition": "Zustand",
        "note": "Nachricht",
        "images": "Bilder",
    }
    error = f"{labels.get(field, 'Eingabe')} fehlt oder ist ungültig."
    if request.url.path == "/hilfe":
        response = help_response(request, error=error, form_values=values, error_field=field)
    else:
        slug = request.path_params.get("room_slug", "")
        with db_connect() as conn:
            room = load_room_by_slug(conn, slug)
        if room is None:
            return public_failure(request, "Dieser Raum ist nicht verfügbar.", 404)
        response = room_form_response(
            request, room, error=error, form_values=values, error_field=field
        )
    response.status_code = 422
    return response


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    """Startseite: zeigt alle aktiven Räume als Auswahl an."""

    with db_connect() as conn:
        rooms = load_active_rooms(conn)
        has_read_access = has_reader_access(conn, request)

    return templates.TemplateResponse(
        request=request,
        name="room_index.html",
        context=page_context(
            request, "public", "rooms", rooms=rooms, has_read_access=has_read_access
        ),
    )


@router.get("/r/{room_slug}", response_class=HTMLResponse)
def room_form(request: Request, room_slug: str):
    """Formularseite für einen bestimmten Raum."""

    with db_connect() as conn:
        room = load_room_by_slug(conn, room_slug)

    if room is None:
        return public_failure(
            request,
            "Dieser Raum ist nicht verfügbar. Wähle bitte einen Raum aus der Übersicht.",
            404,
        )

    return room_form_response(request, room)


@router.post("/r/{room_slug}/submit", dependencies=[Depends(require_same_origin)])
async def submit_usage(
    request: Request,
    room_slug: str,
    background_tasks: BackgroundTasks,
    person_name: str = Form(...),
    house_group: str = Form(...),
    house_number: str = Form(...),
    condition: str = Form(...),
    remark: str = Form(""),
    images: list[UploadFile] = File(default=[]),
):
    """Verarbeitet das Nutzungsformular eines Raums."""

    form_data = await request.form()
    return await run_in_threadpool(
        save_usage,
        request,
        room_slug,
        background_tasks,
        form_data,
        person_name,
        house_group,
        house_number,
        condition,
        remark,
        images,
    )


def save_usage(
    request: Request,
    room_slug: str,
    background_tasks: BackgroundTasks,
    form_data: FormData,
    person_name: str,
    house_group: str,
    house_number: str,
    condition: str,
    remark: str,
    images: list[UploadFile],
):
    """SQLite, Pillow und Dateisystem laufen zusammen im Worker-Thread."""
    person_name = person_name.strip()
    house_group = house_group.strip().upper()
    house_number = house_number.strip()
    house = f"{house_group}{house_number}"
    condition = condition.strip()
    remark = remark.strip()

    with db_connect() as conn:
        room = load_room_by_slug(conn, room_slug)
    if room is None:
        return public_failure(
            request,
            "Dieser Raum ist nicht verfügbar. Wähle bitte einen Raum aus der Übersicht.",
            404,
        )

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

    if house_group not in HOUSE_GROUPS or not re.fullmatch(r"[0-9]+", house_number):
        return room_form_response(request, room, error="Haus ungültig", form_values=form_values)

    if len(house) > MAX_HOUSE_LENGTH or len(house_number) > MAX_HOUSE_NUMBER_LENGTH:
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
        validated_images = validate_image_uploads(images)
    except UploadValidationError as exc:
        return room_form_response(request, room, error=str(exc), form_values=form_values)
    except OSError:
        return public_failure(
            request, "Upload derzeit nicht lesbar. Bitte später erneut versuchen.", 503
        )

    started_at = now_iso()
    saved_paths = []
    saved = False
    try:
        with db_connect() as conn:
            # Serialisiert Quotenprüfung und Dateipublikation über alle Worker.
            conn.execute("BEGIN IMMEDIATE")
            used_bytes = (
                sum(path.stat().st_size for path in UPLOAD_DIR.iterdir() if path.is_file())
                if validated_images
                else 0
            )
            if (
                validated_images
                and used_bytes + sum(len(image.data) for image in validated_images)
                > MAX_UPLOAD_STORAGE_BYTES
            ):
                raise UploadValidationError(
                    "Der Bildspeicher ist voll. Bitte ohne Bilder speichern oder die Administration informieren."
                )
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
                    json.dumps(extra_field_values, ensure_ascii=False)
                    if extra_field_values
                    else None,
                    started_at,
                ),
            )
            session_id = cur.lastrowid

            for image in validated_images:
                target = UPLOAD_DIR / image.filename
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=UPLOAD_DIR,
                    prefix=".upload-",
                    suffix=".tmp",
                    delete=False,
                ) as stream:
                    staging = Path(stream.name)
                    saved_paths.append(staging)
                    stream.write(image.data)
                # Atomar publizieren, ohne eine bereits existierende Datei zu überschreiben.
                os.link(staging, target)
                saved_paths.append(target)
                staging.unlink()

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
        saved = True
    except (sqlite3.Error, OSError, UploadValidationError) as exc:
        if isinstance(exc, UploadValidationError):
            return room_form_response(request, room, error=str(exc), form_values=form_values)
        logger.error("Nutzung konnte nicht gespeichert werden (%s)", type(exc).__name__)
        return public_failure(
            request, "Speichern derzeit nicht möglich. Bitte später erneut versuchen.", 503
        )

    finally:
        if not saved:
            for path in saved_paths:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logger.error("Upload-Restdatei konnte nicht entfernt werden")

    background_tasks.add_task(
        notify_usage_safely,
        room_name=room["name"],
        person_name=person_name,
        house=house,
        condition=condition,
        remark=remark,
        started_at=started_at,
        image_count=len(validated_images),
    )

    thanks_url = f"/thanks?raum={quote(room_slug, safe='')}"
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
        request=request,
        name="thanks.html",
        context=page_context(request, "public", "rooms", room=room),
    )


@router.get("/hilfe", response_class=HTMLResponse)
def help_page(request: Request):
    """Zeigt das öffentliche Formular ohne gespeicherte Nachrichten."""

    return help_response(request, saved=request.query_params.get("gespeichert") == "1")


@router.post("/hilfe", dependencies=[Depends(require_same_origin)])
def submit_help_message(request: Request, person_name: str = Form(""), note: str = Form(...)):
    """Speichert eine Nachricht aus Hilfe & Infos."""

    person_name = person_name.strip()
    note = note.strip()

    form_values = {"person_name": person_name, "note": note}

    if not note:
        return help_response(request, error="Nachricht fehlt", form_values=form_values)
    if len(person_name) > MAX_NAME_LENGTH:
        return help_response(
            request,
            error=length_error("Name", MAX_NAME_LENGTH),
            form_values=form_values,
        )
    if len(note) > MAX_GENERAL_NOTE_LENGTH:
        return help_response(
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

    return RedirectResponse("/hilfe?gespeichert=1", status_code=303)


@router.get("/datenschutz", response_class=HTMLResponse)
def privacy(request: Request):
    """Datenschutzseite."""

    return templates.TemplateResponse(
        request=request,
        name="privacy.html",
        context=page_context(
            request, "meta", "privacy", reader_session_days=READER_SESSION_SECONDS // 86400
        ),
    )


@router.get("/logbuch", response_class=HTMLResponse, dependencies=[Depends(require_reader)])
def logbook(request: Request):
    """Globale Reader-Ansicht aller nicht gelöschten Nutzungen."""

    selected_room = request.query_params.get("raum", "").strip()
    selected_condition = request.query_params.get("zustand", "").strip()
    search = request.query_params.get("q", "").strip()
    page_raw = request.query_params.get("seite", "1")
    valid_page = (
        page_raw.isascii()
        and page_raw.isdecimal()
        and len(page_raw) <= 7
        and 1 <= int(page_raw) <= 1000000
    )
    page = int(page_raw) if valid_page else 1
    logbook_url = "/admin/logbuch" if request_is_admin(request) else "/logbuch"

    with db_connect() as conn:
        rooms = load_active_rooms(conn)
        filter_error = ""
        if not valid_page:
            filter_error = "Bitte wähle eine gültige Logbuchseite."
        elif selected_room and selected_room not in {room["slug"] for room in rooms}:
            filter_error = "Dieser Raumfilter ist nicht verfügbar. Bitte wähle einen aktiven Raum."
        elif selected_condition and selected_condition not in WORKSHOP_CONDITIONS:
            filter_error = "Bitte wähle einen gültigen Zustand."
        elif len(search) > 100:
            filter_error = "Die Suche darf maximal 100 Zeichen lang sein."
        entries = (
            []
            if filter_error
            else fetch_booking_entries(
                conn,
                selected_room=selected_room,
                selected_condition=selected_condition,
                search=search,
                limit=21,
                offset=(page - 1) * 20,
                literal_search=True,
            )
        )

    def page_url(number):
        params = {
            key: value
            for key, value in {
                "raum": selected_room,
                "q": search,
                "zustand": selected_condition,
                "seite": str(number),
            }.items()
            if value
        }
        return logbook_url + "?" + urlencode(params)

    def room_url(slug):
        query = urlencode(
            {
                key: value
                for key, value in {"raum": slug, "q": search, "zustand": selected_condition}.items()
                if value
            }
        )
        return logbook_url + ("?" + query if query else "")

    return templates.TemplateResponse(
        request=request,
        name="logbook.html",
        context=page_context(
            request,
            "public",
            "logbook",
            entries=entries[:20],
            rooms=rooms,
            selected_room=selected_room,
            logbook_url=logbook_url,
            conditions=WORKSHOP_CONDITIONS,
            selected_condition=selected_condition,
            search=search,
            filter_error=filter_error,
            has_filters=bool(selected_room or selected_condition or search),
            page=page,
            newer_url=page_url(page - 1) if page > 1 else "",
            older_url=page_url(page + 1) if len(entries) > 20 else "",
            first_url=page_url(1),
            room_urls={room["slug"]: room_url(room["slug"]) for room in rooms},
            all_rooms_url=room_url(""),
        ),
        status_code=400 if filter_error else 200,
    )


@router.get("/rooms/latest-status", dependencies=[Depends(require_reader)])
def latest_room_status():
    with db_connect() as conn:
        return fetch_latest_room_status(conn)


def room_bookings_response(request: Request, room: dict) -> HTMLResponse:
    """HTML-Fragment; ausschließlich aus geschützten Reader-/Admin-Routen aufrufen."""
    with db_connect() as conn:
        entries = fetch_booking_entries(conn, selected_room=room["slug"], limit=3)
    return templates.TemplateResponse(
        request=request,
        name="_booking_cards.html",
        context={"entries": entries},
    )


@router.get("/r/{room_slug}/recent-bookings", dependencies=[Depends(require_reader)])
def room_recent_bookings(request: Request, room_slug: str):
    with db_connect() as conn:
        room = load_room_by_slug(conn, room_slug)
    if room is None:
        raise HTTPException(404, "Raum nicht gefunden.")
    return room_bookings_response(request, room)


@router.get("/r/{room_slug}/qr.pdf", dependencies=[Depends(require_reader)])
def room_qr_pdf(request: Request, room_slug: str):
    """Erstellt und liefert ein PDF mit QR-Code für einen bestimmten Raum."""

    with db_connect() as conn:
        room = load_room_by_slug(conn, room_slug)

    if room is None:
        return HTMLResponse("Raum nicht gefunden", status_code=404)

    return room_qr_pdf_response(room)


@router.get("/uploads/{filename}", dependencies=[Depends(require_reader)])
def uploaded_file(filename: str):
    """Liefert hochgeladene Bilder aus."""

    if not UPLOAD_FILENAME_PATTERN.fullmatch(filename):
        return HTMLResponse("Datei nicht gefunden", status_code=404)
    with db_connect() as conn:
        image = fetch_image_by_filename(conn, filename)
    if image is None:
        return HTMLResponse("Datei nicht gefunden", status_code=404)

    path = UPLOAD_DIR / filename
    if path.is_symlink() or not path.is_file():
        return HTMLResponse("Datei nicht gefunden", status_code=404)
    content_type = image["content_type"]
    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        content_type = "application/octet-stream"
    return FileResponse(path, media_type=content_type)


@router.post("/r/{room_slug}/access", dependencies=[Depends(require_same_origin)])
async def room_access(request: Request, room_slug: str):
    """Fragment-Token ausschließlich im begrenzten JSON-POST entgegennehmen."""
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
        raise HTTPException(415, "JSON-Anfrage erforderlich.")
    raw = await request.body()
    if len(raw) > 1024:
        raise HTTPException(400, "Ungültige Raumzugang-Anfrage.")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError):
        raise HTTPException(400, "Ungültige Raumzugang-Anfrage.") from None
    token = payload.get("token") if isinstance(payload, dict) else None
    if not isinstance(token, str):
        raise HTTPException(403, "Raumzugang ungültig oder abgelaufen.")
    return await run_in_threadpool(exchange_room_token, request, room_slug, token)


@router.post(
    "/r/{room_slug}/access-link",
    dependencies=[Depends(require_reader), Depends(require_same_origin)],
)
def copy_access_link(room_slug: str):
    """Geheimer Link nur nach bewusster Aktion und gültiger globaler Berechtigung."""
    with db_connect() as conn:
        room = load_room_by_slug(conn, room_slug)
    if room is None:
        raise HTTPException(404, "Raum nicht gefunden")
    return {"url": room_qr_url(room)}
