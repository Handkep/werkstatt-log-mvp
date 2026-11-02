import shutil
import subprocess
from io import BytesIO

import pytest
import zxingcpp
from PIL import Image
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

from app.capabilities import room_qr_url
from app.services import pdf
from app.utils import configured_public_base_url
from tests.conftest import admin_auth


def test_pdf_and_dynamic_room_text(client):
    response = client.get("/r/sauna/qr.pdf", auth=admin_auth(client))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["content-disposition"] == 'attachment; filename="zelter5-qr-sauna.pdf"'
    reader = PdfReader(BytesIO(response.content))
    text = reader.pages[0].extract_text()
    assert "Sauna" in text and "Werkstatt" not in text
    assert client.get("/r/missing/qr.pdf", auth=admin_auth(client)).status_code == 404


@pytest.mark.parametrize(
    "base",
    [
        "javascript:alert(1)",
        "//evil.example",
        "https://user:pass@example.com",
        "https://example.com?x=1",
        "https://example.com/#x",
        "https://exam ple.com",
    ],
)
def test_invalid_public_base_url(monkeypatch, base):
    monkeypatch.setenv("PUBLIC_BASE_URL", base)
    with pytest.raises(ValueError):
        configured_public_base_url()


def test_public_base_url_and_slug_encoding(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://rooms.example/base/")
    assert room_qr_url({"id": 1, "slug": "Sauna/ä", "qr_key_version": 1}).startswith(
        "https://rooms.example/base/r/Sauna%2F%C3%A4#access="
    )


POSTER_CASES = [
    ("Werkstatt", "werkstatt", 0),
    ("Dachterrasse", "dachterrasse", 0),
    ("Sommerküche", "sommerkueche", 0),
    ("Sauna", "sauna", 0),
    ("Ruheraum", "ruheraum", 0),
    ("Werkstatt für Holz, Metall & Reparaturen – ÄÖÜ äöü ß Ā Ł", "lang", 100),
    (
        "Gemeinschaftsraum für Reparaturen, Besprechungen und gemeinsame Projekte " * 3,
        "sehr-lang",
        400,
    ),
    ("Raum <Nord> & Süd", "sonderzeichen", 0),
]


def test_only_three_finders_are_rounded_with_exact_dimensions():
    class Path:
        def __init__(self):
            self.rectangles = []

        def rect(self, *args):
            self.rectangles.append(args)

    class Canvas:
        def __init__(self):
            self.path = Path()
            self.rounded = []

        def beginPath(self):
            return self.path

        def roundRect(self, *args, **kwargs):
            self.rounded.append(args)

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    url = "https://rooms.example/r/werkstatt#access=synthetic"
    matrix = pdf.qr_matrix(url)
    target = Canvas()
    pdf.draw_qr(target, url, 0, 0, size=len(matrix))
    finders = ((4, 4), (4, len(matrix) - 11), (len(matrix) - 11, 4))
    assert pdf.finder_origins(len(matrix)) == finders
    expected = []
    for row, modules in enumerate(matrix):
        for col, black in enumerate(modules):
            if black and not any(r <= row < r + 7 and c <= col < c + 7 for r, c in finders):
                expected.append((col, len(matrix) - row - 1, 1, 1))
    assert target.path.rectangles == expected
    assert len(target.rounded) == 9
    for index, (row, col) in enumerate(finders):
        bottom = len(matrix) - row - 7
        assert target.rounded[index * 3 : index * 3 + 3] == [
            (col, bottom, 7, 7, 1),
            (col + 1, bottom + 1, 5, 5, 0.75),
            (col + 2, bottom + 2, 3, 3, 0.5),
        ]


@pytest.mark.parametrize("name,slug,padding", POSTER_CASES)
@pytest.mark.parametrize("dpi", [150, 300])
def test_rendered_poster_is_single_page_embedded_vector_and_decodes(
    tmp_path, name, slug, padding, dpi
):
    tool = shutil.which("pdftoppm")
    assert tool, "PDF-Prüfung benötigt Poppler/pdftoppm."
    url = f"https://rooms.example/{'test-path/' * (padding // 10)}r/{slug}#access=synthetic-test-key-only"
    payload = pdf.build_room_qr_pdf({"name": name}, url)
    reader = PdfReader(BytesIO(payload))
    assert len(reader.pages) == 1
    page = reader.pages[0]
    assert float(page.mediabox.width) == pytest.approx(A4[0], abs=0.01)
    assert float(page.mediabox.height) == pytest.approx(A4[1], abs=0.01)
    text = page.extract_text()
    assert " ".join(name.split()) in " ".join(text.split())
    assert text.count("Zelter5 Raumlog") == 1
    assert "Nutzung dokumentieren" in text
    assert "Raumlogbücher" not in text and "01" not in text
    assert all(
        label in text and " ".join(description.split()) in " ".join(text.split())
        for label, description in pdf.STEPS
    )
    assert url not in text and "synthetic-test-key-only" not in text
    assert url not in str(reader.metadata)
    assert reader.metadata.title == f"{name} – Zelter5 Raumlog"
    assert not page.images  # QR ist vollständig vektorbasiert.
    names = []
    for ref in page["/Resources"]["/Font"].values():
        font = ref.get_object()
        assert "/FontDescriptor" in font
        assert "/FontFile2" in font["/FontDescriptor"]
        names.append(str(font["/BaseFont"]))
    assert any("NotoSerifDisplay-Medium" in name for name in names)
    assert any("NotoSerifDisplay-Bold" in name for name in names)
    assert any("GoogleSansFlex-Regular" in name for name in names)
    source, prefix = tmp_path / "poster.pdf", tmp_path / "render"
    source.write_bytes(payload)
    subprocess.run(
        [tool, "-r", str(dpi), "-singlefile", "-png", str(source), str(prefix)],
        check=True,
        capture_output=True,
    )
    with Image.open(prefix.with_suffix(".png")) as rendered:
        decoded = zxingcpp.read_barcodes(rendered)
        assert len(decoded) == 1 and decoded[0].text == url
        matrix = pdf.qr_matrix(url)
        gray = rendered.convert("L")
        unit = pdf.QR_SIZE / len(matrix) * dpi / 72
        left = (A4[0] - pdf.QR_SIZE) / 2 * dpi / 72
        top = pdf.QR_TOP * dpi / 72
        # Gesamtes Raster inkl. weißer Ruhe-/Trennbereiche und Funktionsmuster.
        for row, modules in enumerate(matrix):
            for col, black in enumerate(modules):
                value = gray.getpixel(
                    (int(left + (col + 0.5) * unit), int(top + (row + 0.5) * unit))
                )
                assert (value < 128) == black, (row, col)
        # Auch bei langen Titeln bleiben sämtliche Glyphen innerhalb der Druckränder.
    positions = []

    def visitor(text, cm, tm, font, size):
        if text.strip():
            positions.append((text, cm[4] + tm[4], cm[5] + tm[5], size))

    page.extract_text(visitor_text=visitor)
    assert all(x >= 20 * mm - 0.1 and y >= 20 * mm - 0.1 for _, x, y, _ in positions), positions

    # Gemeinsame Grundlinie, drei gleich breite Spalten, deutlich größerer Raumname.
    headings = [
        (text.strip(), x, y, size)
        for text, x, y, size in positions
        if text.strip() in {label for label, _ in pdf.STEPS}
    ]
    assert len(headings) == 3
    assert len({round(y, 2) for _, _, y, _ in headings}) == 1
    assert all(size == 15 for _, _, _, size in headings)
    from reportlab.pdfbase import pdfmetrics

    centers = [
        x + pdfmetrics.stringWidth(text, pdf.PDF_FONTS["semibold"], size) / 2
        for text, x, _, size in headings
    ]
    assert centers[1] == pytest.approx(A4[0] / 2, abs=0.01)
    assert centers[1] - centers[0] == pytest.approx(centers[2] - centers[1], abs=0.01)
    if name == "Werkstatt":
        assert any(text.strip() == "Werkstatt" and size == 60 for text, _, _, size in positions)

    # Keine Textzeile ragt über den rechten Druckrand oder in die nächste Spalte.
    def check_line(text, cm, tm, font, size):
        if not text.strip():
            return
        font_name = str(font["/BaseFont"]).split("+")[-1]
        right = (
            cm[4]
            + tm[4]
            + max(
                pdfmetrics.stringWidth(line, font_name, size) for line in text.strip().splitlines()
            )
        )
        assert right <= A4[0] - 20 * mm + 0.1
        if cm[5] + tm[5] < A4[1] - 218 * mm:
            left = cm[4] + tm[4]
            column_width = (A4[0] - 40 * mm - 16 * mm) / 3
            column = min(
                range(3), key=lambda i: abs(left - (20 * mm + i * (column_width + 8 * mm)))
            )
            column_left = 20 * mm + column * (column_width + 8 * mm)
            assert right <= column_left + column_width + 0.1
            assert (left + right) / 2 == pytest.approx(column_left + column_width / 2, abs=0.02)

    page.extract_text(visitor_text=check_line)
