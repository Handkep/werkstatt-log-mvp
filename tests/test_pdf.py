import pytest

from app.capabilities import room_qr_url
from app.services import pdf
from app.utils import configured_public_base_url
from tests.conftest import admin_auth


def test_pdf_and_dynamic_room_text(client, monkeypatch):
    texts = []
    original = pdf.draw_paragraph

    def record(*args, **kwargs):
        texts.append(args[1])
        return original(*args, **kwargs)

    monkeypatch.setattr(pdf, "draw_paragraph", record)
    response = client.get("/r/sauna/qr.pdf", auth=admin_auth(client))
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-")
    assert response.headers["content-type"] == "application/pdf"
    assert "Sauna" in texts[0] and "Werkstatt" not in texts[0]
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
