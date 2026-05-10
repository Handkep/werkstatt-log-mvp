"""QR-PDF-Erzeugung."""

from html import escape
from io import BytesIO
from pathlib import Path

import qrcode
from fontTools.ttLib import TTCollection
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from app.config import FONT_DIR, logger


def find_ttc_subfont_index(ttc_path: Path, wanted_style: str) -> int | None:
    """Sucht in einer .ttc-Datei den Index eines bestimmten Schriftschnitts."""

    collection = TTCollection(str(ttc_path))

    for index, font in enumerate(collection.fonts):
        styles = []

        for name in font["name"].names:
            if name.nameID in {2, 4}:
                try:
                    styles.append(name.toUnicode())
                except UnicodeDecodeError:
                    pass

        joined = " ".join(styles).lower()
        if wanted_style.lower() in joined:
            return index

    return None


def register_pdf_fonts() -> dict:
    """Registriert bevorzugt Inter und fällt sonst auf Helvetica zurück."""

    inter_ttc = FONT_DIR / "Inter.ttc"

    if inter_ttc.exists():
        regular_index = find_ttc_subfont_index(inter_ttc, "Regular")
        semibold_index = find_ttc_subfont_index(inter_ttc, "SemiBold")
        bold_index = find_ttc_subfont_index(inter_ttc, "Bold")

        if regular_index is not None and semibold_index is not None and bold_index is not None:
            try:
                pdfmetrics.registerFont(
                    TTFont("Inter-Regular", str(inter_ttc), subfontIndex=regular_index)
                )
                pdfmetrics.registerFont(
                    TTFont("Inter-SemiBold", str(inter_ttc), subfontIndex=semibold_index)
                )
                pdfmetrics.registerFont(
                    TTFont("Inter-Bold", str(inter_ttc), subfontIndex=bold_index)
                )
                pdfmetrics.registerFontFamily(
                    "Inter",
                    normal="Inter-Regular",
                    bold="Inter-Bold",
                    italic="Inter-Regular",
                    boldItalic="Inter-Bold",
                )
                return {
                    "regular": "Inter-Regular",
                    "semibold": "Inter-SemiBold",
                    "bold": "Inter-Bold",
                }
            except Exception:
                logger.exception("Inter-PDF-Schriften konnten nicht registriert werden.")

    return {
        "regular": "Helvetica",
        "semibold": "Helvetica-Bold",
        "bold": "Helvetica-Bold",
    }


PDF_FONTS = register_pdf_fonts()


def make_qr_image(data: str):
    """Erzeugt ein QR-Code-Bild für den übergebenen Text bzw. die URL."""

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def draw_centered_text(pdf_canvas: canvas.Canvas, text: str, y: float, font: str, size: int) -> None:
    """Zeichnet eine Textzeile horizontal zentriert auf eine A4-PDF-Seite."""

    page_width, _ = A4
    pdf_canvas.setFont(font, size)
    text_width = pdf_canvas.stringWidth(text, font, size)
    pdf_canvas.drawString((page_width - text_width) / 2, y, text)


def draw_paragraph(
    pdf_canvas: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    font_name: str = "Helvetica",
    font_size: int = 11,
    leading: int | None = None,
    alignment=TA_CENTER,
    text_color="#111827",
) -> None:
    """Zeichnet einen mehrzeiligen Textblock mit sauberem Umbruch."""

    if leading is None:
        leading = int(font_size * 1.35)

    safe_text = escape(text).replace("\n", "<br/>")

    style = ParagraphStyle(
        name="PdfParagraph",
        fontName=font_name,
        fontSize=font_size,
        leading=leading,
        alignment=alignment,
        textColor=HexColor(text_color),
        spaceAfter=0,
        spaceBefore=0,
    )

    paragraph = Paragraph(safe_text, style)
    paragraph.wrapOn(pdf_canvas, width, height)
    paragraph.drawOn(pdf_canvas, x, y)


def build_room_qr_pdf(room: dict, room_url: str) -> bytes:
    """Erstellt ein einseitiges PDF mit QR-Code für einen Raum."""

    buffer = BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4

    room_name = room.get("name", "Raum")
    pdf_canvas.setTitle(f"QR-Code {room_name} - Zelter5 Raumlog")

    draw_centered_text(
        pdf_canvas,
        "Zelter5 Raumlog",
        page_height - 35 * mm,
        PDF_FONTS["bold"],
        40,
    )
    draw_centered_text(
        pdf_canvas,
        room_name,
        page_height - 48 * mm,
        PDF_FONTS["regular"],
        15,
    )

    qr_image = make_qr_image(room_url)
    qr_size = 120 * mm
    qr_x = (page_width - qr_size) / 2
    qr_y = page_height - 190 * mm

    pdf_canvas.drawImage(
        ImageReader(qr_image),
        qr_x,
        qr_y,
        width=qr_size,
        height=qr_size,
        preserveAspectRatio=True,
        mask="auto",
    )

    intro_text = (
        "Damit die Werkstatt sauber und ordentlich bleibt, bitten wir dich,\n"
        "vor der Nutzung den QR-Code zu scannen und das Formular auszufüllen."
    )

    draw_paragraph(
        pdf_canvas,
        intro_text,
        32 * mm,
        qr_y - 26 * mm,
        page_width - 64 * mm,
        24 * mm,
        font_name=PDF_FONTS["bold"],
        font_size=11,
        leading=15,
        alignment=TA_CENTER,
        text_color="#374151",
    )

    pdf_canvas.showPage()
    pdf_canvas.save()

    buffer.seek(0)
    return buffer.getvalue()
