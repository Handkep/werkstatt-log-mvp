"""Einseitige Raumaushänge mit lokalen Schriften und gerundetem Vektor-QR."""

from html import escape
from io import BytesIO

import qrcode
from fastapi.responses import StreamingResponse
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from app.capabilities import room_qr_url
from app.config import FONT_DIR
from app.utils import safe_download_slug

QR_SIZE = 110 * mm
QR_BORDER = 4
QR_TOP = 90 * mm
INK = "#17191D"
STEPS = (
    ("Scannen", "Öffne den QR-Code mit deiner Handykamera."),
    ("Eintragen", "Fülle das Formular für diesen Raum aus."),
    ("Speichern", "Tippe auf „Nutzung speichern“."),
)


def register_pdf_fonts() -> dict:
    """Statische, lokal mitgelieferte TTF-Schnitte einbetten."""
    fonts = {
        "regular": "GoogleSansFlex-Regular",
        "semibold": "GoogleSansFlex-SemiBold",
        "bold": "GoogleSansFlex-Bold",
        "display": "NotoSerifDisplay-Medium",
        "brand": "NotoSerifDisplay-Bold",
    }
    for name in fonts.values():
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / f"{name}.ttf")))
    pdfmetrics.registerFontFamily(
        "GoogleSansFlex",
        normal=fonts["regular"],
        bold=fonts["bold"],
        italic=fonts["regular"],
        boldItalic=fonts["bold"],
    )
    return fonts


PDF_FONTS = register_pdf_fonts()


def qr_matrix(data: str) -> list[list[bool]]:
    """Bisherigen QR-Inhalt und Fehlerkorrektur M mit vier Modulen Ruhezone erzeugen."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=QR_BORDER,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr.get_matrix()


def finder_origins(matrix_size: int) -> tuple[tuple[int, int], ...]:
    """Obere linke Rasterpositionen der drei 7×7-Finder, einschließlich Ruhezone."""
    start, end = QR_BORDER, matrix_size - QR_BORDER - 7
    return ((start, start), (start, end), (end, start))


def draw_qr(pdf_canvas: canvas.Canvas, data: str, x: float, y: float, size=QR_SIZE) -> None:
    """Eckige Module und drei zusammenhängende Finder mit gerundeten Konturen."""
    matrix = qr_matrix(data)
    unit = size / len(matrix)
    finders = finder_origins(len(matrix))
    path = pdf_canvas.beginPath()
    for row, modules in enumerate(matrix):
        for col, black in enumerate(modules):
            in_finder = any(r <= row < r + 7 and c <= col < c + 7 for r, c in finders)
            if black and not in_finder:
                path.rect(x + col * unit, y + (len(matrix) - row - 1) * unit, unit, unit)
    pdf_canvas.saveState()
    pdf_canvas.setFillColorRGB(0, 0, 0)
    pdf_canvas.drawPath(path, stroke=0, fill=1, fillMode=1)
    for row, col in finders:
        left = x + col * unit
        bottom = y + (len(matrix) - row - 7) * unit
        # Weißer Innenraum und schwarzer Kern bilden einen gleichmäßig weichen Finder.
        for inset, side, radius, shade in ((0, 7, 1, 0), (1, 5, 0.75, 1), (2, 3, 0.5, 0)):
            pdf_canvas.setFillColorRGB(shade, shade, shade)
            pdf_canvas.roundRect(
                left + inset * unit,
                bottom + inset * unit,
                side * unit,
                side * unit,
                radius * unit,
                stroke=0,
                fill=1,
            )
    pdf_canvas.restoreState()


def paragraph(text, font, size, leading, alignment=TA_CENTER):
    """Raumtexte als Text behandeln, nicht als ReportLab-Markup."""
    return Paragraph(
        escape(text).replace("\n", "<br/>"),
        ParagraphStyle(
            "Poster",
            fontName=font,
            fontSize=size,
            leading=leading,
            alignment=alignment,
            textColor=HexColor(INK),
            splitLongWords=True,
        ),
    )


def paragraph_has_overflow(block: Paragraph) -> bool:
    """ReportLab toleriert kleine Zeilenüberläufe; beim Aushang strikt vermeiden."""
    return any(
        (line[0] if isinstance(line, tuple) else line.extraSpace) < -0.001
        for line in block.blPara.lines
    )


def draw_text(
    pdf_canvas, text, x, top, width, *, font, size, leading, max_height, alignment=TA_CENTER
):
    block = paragraph(text, font, size, leading, alignment)
    _, height = block.wrap(width, max_height)
    if height > max_height + 0.01 or paragraph_has_overflow(block):
        raise ValueError("Text passt nicht in den vorgesehenen PDF-Bereich.")
    block.drawOn(pdf_canvas, x, top - height)
    return height


def build_room_qr_pdf(room: dict, room_url: str) -> bytes:
    """Ein A4-Aushang, ohne sichtbaren Zugangsschlüssel und ohne Rastergrafik."""
    buffer = BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=A4, initialFontName=PDF_FONTS["regular"])
    width, height = A4
    margin = 20 * mm
    content_width = width - 2 * margin
    room_name = room.get("name") or "Raum"
    pdf_canvas.setTitle(f"{room_name} – Zelter5 Raumlog")
    pdf_canvas.setAuthor("Zelter5 Raumlog")
    pdf_canvas.setSubject("QR-Aushang zur Raumnutzung")
    pdf_canvas.setFillColorRGB(1, 1, 1)
    pdf_canvas.rect(0, 0, width, height, stroke=0, fill=1)

    draw_text(
        pdf_canvas,
        "Zelter5 Raumlog",
        margin,
        height - margin,
        content_width,
        font=PDF_FONTS["brand"],
        size=16,
        leading=21,
        max_height=25,
    )
    title_top, title_height = height - 36 * mm, 35 * mm
    # Feste Titelzone: dynamisch umbrechen, alle weiteren Blöcke bleiben stabil.
    for half_points in range(120, 15, -1):
        title_size = half_points / 2
        block = paragraph(room_name, PDF_FONTS["display"], title_size, title_size * 1.15)
        _, used_height = block.wrap(content_width, title_height)
        if used_height <= title_height and not paragraph_has_overflow(block):
            block.drawOn(pdf_canvas, margin, title_top - used_height)
            break
    else:
        raise ValueError("Raumname ist zu lang für einen einseitigen Aushang.")
    draw_text(
        pdf_canvas,
        "Nutzung dokumentieren",
        margin,
        height - 76 * mm,
        content_width,
        font=PDF_FONTS["regular"],
        size=14,
        leading=18,
        max_height=20,
    )

    draw_qr(pdf_canvas, room_url, (width - QR_SIZE) / 2, height - QR_TOP - QR_SIZE)

    gap = 8 * mm
    column_width = (content_width - 2 * gap) / 3
    top = height - 218 * mm
    for index, (label, description) in enumerate(STEPS):
        left = margin + index * (column_width + gap)
        draw_text(
            pdf_canvas,
            label,
            left,
            top,
            column_width,
            font=PDF_FONTS["semibold"],
            size=15,
            leading=19,
            max_height=20,
            alignment=TA_CENTER,
        )
        draw_text(
            pdf_canvas,
            description,
            left,
            top - 27,
            column_width,
            font=PDF_FONTS["regular"],
            size=12,
            leading=16,
            max_height=48 * mm,
            alignment=TA_CENTER,
        )

    pdf_canvas.showPage()
    pdf_canvas.save()
    return buffer.getvalue()


def room_qr_pdf_response(room: dict) -> StreamingResponse:
    """Ein gemeinsamer Renderer für Reader- und Admin-Routen."""
    pdf_bytes = build_room_qr_pdf(room, room_qr_url(room))
    filename = f"zelter5-qr-{safe_download_slug(room['slug'])}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )
