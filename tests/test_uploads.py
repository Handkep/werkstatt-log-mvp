import io
import sqlite3
import struct
import zlib

import pytest
from PIL import Image, PngImagePlugin

from app import db
from app.routes import public
from app.services import uploads
from tests.conftest import VALID, admin_auth
from tests.test_security import csrf


def image_bytes(fmt="PNG", size=(24, 20), **kwargs):
    out = io.BytesIO()
    with Image.new("RGB", size, "red") as image:
        image.save(out, format=fmt, **kwargs)
    return out.getvalue()


def post_image(client, data, name="image.png"):
    return client.post(
        "/r/werkstatt/submit",
        data=VALID,
        files={"images": (name, data, "image/png")},
        follow_redirects=False,
    )


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_valid_images_and_authorization(client, paths, fmt):
    response = post_image(client, image_bytes(fmt))
    assert response.status_code == 303
    with db.db_connect() as conn:
        filename = conn.execute("SELECT filename FROM usage_images").fetchone()[0]
    url = f"/uploads/{filename}"
    assert client.get(url).status_code == 403
    response = client.get(url, auth=admin_auth(client))
    assert response.status_code == 200
    assert "no-store" in response.headers["cache-control"]
    with Image.open(io.BytesIO(response.content)) as image:
        image.load()
        assert image.format == fmt
    assert client.get("/uploads/" + "a" * 32 + ".png", auth=admin_auth(client)).status_code == 404
    token = csrf(client)
    client.post("/admin/session/1/delete", auth=admin_auth(client), data={"csrf_token": token})
    assert client.get(url, auth=admin_auth(client)).status_code == 404
    assert (paths[1] / filename).exists()  # Soft-Delete entfernt keine Datei.


def test_orphans_missing_files_and_symlinks(client, paths):
    orphan = paths[1] / ("a" * 32 + ".jpg")
    orphan.write_bytes(image_bytes("JPEG"))
    assert client.get(f"/uploads/{orphan.name}", auth=admin_auth(client)).status_code == 404
    post_image(client, image_bytes())
    with db.db_connect() as conn:
        filename = conn.execute("SELECT filename FROM usage_images").fetchone()[0]
    target = paths[1] / filename
    target.unlink()
    assert client.get(f"/uploads/{filename}", auth=admin_auth(client)).status_code == 404
    target.symlink_to(orphan)
    assert client.get(f"/uploads/{filename}", auth=admin_auth(client)).status_code == 404


@pytest.mark.parametrize(
    "bad",
    [
        b"not an image",
        image_bytes("GIF"),
        image_bytes("JPEG")[:-2],
        image_bytes("PNG")[:-6],
        image_bytes("PNG")[:45],
        b"<svg xmlns='http://www.w3.org/2000/svg'/>",
    ],
)
def test_invalid_uploads_leave_no_data(client, paths, bad):
    assert post_image(client, bad).status_code == 400
    with db.db_connect() as conn:
        assert conn.execute("SELECT count(*) FROM usage_sessions").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM usage_images").fetchone()[0] == 0
    assert list(paths[1].iterdir()) == []


def test_corrupt_png_with_valid_crc_fails_decoding(client):
    data = bytearray(image_bytes())
    offset = 8
    while offset < len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        if data[offset + 4 : offset + 8] == b"IDAT":
            data[offset + 8 : offset + 8 + length] = b"\xff" * length
            struct.pack_into(
                ">I", data, offset + 8 + length, zlib.crc32(data[offset + 4 : offset + 8 + length])
            )
            break
        offset += length + 12
    assert post_image(client, bytes(data)).status_code == 400


def test_metadata_removed_and_exif_orientation(client):
    exif = Image.Exif()
    exif[274] = 6
    exif[315] = "PRIVATE AUTHOR"
    assert post_image(client, image_bytes("JPEG", exif=exif)).status_code == 303
    with db.db_connect() as conn:
        filename = conn.execute("SELECT filename FROM usage_images").fetchone()[0]
    content = client.get(f"/uploads/{filename}", auth=admin_auth(client)).content
    with Image.open(io.BytesIO(content)) as image:
        assert image.size == (20, 24)
        assert not image.getexif()
        assert "icc_profile" not in image.info
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Private", "GPS PRIVATE")
    assert post_image(client, image_bytes(pnginfo=metadata)).status_code == 303
    with db.db_connect() as conn:
        filename = conn.execute("SELECT filename FROM usage_images ORDER BY id DESC").fetchone()[0]
    with Image.open(
        io.BytesIO(client.get(f"/uploads/{filename}", auth=admin_auth(client)).content)
    ) as image:
        assert "Private" not in image.info


def test_size_count_dimensions_pixels_and_bombs(client, monkeypatch):
    data = image_bytes()
    monkeypatch.setattr(uploads, "MAX_UPLOAD_SIZE_BYTES", len(data) - 1)
    assert post_image(client, data).status_code == 400
    monkeypatch.setattr(uploads, "MAX_UPLOAD_SIZE_BYTES", 100_000)
    monkeypatch.setattr(uploads, "MAX_IMAGE_DIMENSION", 10)
    assert post_image(client, data).status_code == 400
    monkeypatch.setattr(uploads, "MAX_IMAGE_DIMENSION", 100)
    monkeypatch.setattr(uploads, "MAX_IMAGE_PIXELS", 100)
    assert post_image(client, data).status_code == 400
    monkeypatch.setattr(uploads, "MAX_IMAGE_PIXELS", 10000)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 300)  # warning
    assert post_image(client, data).status_code == 400
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)  # error
    assert post_image(client, data).status_code == 400
    monkeypatch.setattr(uploads, "MAX_UPLOAD_IMAGES", 1)
    assert (
        client.post(
            "/r/werkstatt/submit",
            data=VALID,
            files=[("images", ("a.png", data)), ("images", ("b.png", data))],
        ).status_code
        == 400
    )


def test_storage_limit_includes_existing_orphans(client, paths, monkeypatch):
    (paths[1] / "old-upload").write_bytes(b"0123456789")
    monkeypatch.setattr(public, "MAX_UPLOAD_STORAGE_BYTES", 10)
    assert post_image(client, image_bytes()).status_code == 400
    assert client.post("/r/werkstatt/submit", data=VALID, follow_redirects=False).status_code == 303


@pytest.mark.parametrize("failure", ["write", "database", "commit"])
def test_storage_failures_rollback_and_cleanup(client, paths, monkeypatch, failure):
    from contextlib import contextmanager

    if failure == "write":
        original = public.tempfile.NamedTemporaryFile

        class BrokenStream:
            def __init__(self, stream):
                self.stream, self.name = stream, stream.name

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.stream.close()

            def write(self, data):
                self.stream.write(b"partial")
                raise OSError("disk full")

        def broken(*args, **kwargs):
            return BrokenStream(original(*args, **kwargs))

        monkeypatch.setattr(public.tempfile, "NamedTemporaryFile", broken)
    else:
        original_connect = db.db_connect

        @contextmanager
        def broken_connect():
            with original_connect() as conn:
                if failure == "database":
                    conn.execute(
                        "CREATE TRIGGER fail_images BEFORE INSERT ON usage_images BEGIN SELECT RAISE(ABORT, 'fail'); END"
                    )
                yield conn
                if failure == "commit":
                    raise sqlite3.OperationalError("commit failed")

        # Only persistence context: load-room connection must still work.
        count = 0

        @contextmanager
        def connect():
            nonlocal count
            count += 1
            with broken_connect() if count == 2 else original_connect() as conn:
                yield conn

        monkeypatch.setattr(public, "db_connect", connect)
    assert post_image(client, image_bytes()).status_code == 503
    assert list(paths[1].iterdir()) == []
    with db.db_connect() as conn:
        assert conn.execute("SELECT count(*) FROM usage_sessions").fetchone()[0] == 0


def test_unexpected_storage_error_still_cleans_files(client, paths, monkeypatch):
    def fail(*args):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(public.os, "link", fail)
    with pytest.raises(RuntimeError, match="unexpected"):
        post_image(client, image_bytes())
    assert not list(paths[1].iterdir())
    with db.db_connect() as conn:
        assert conn.execute("SELECT count(*) FROM usage_sessions").fetchone()[0] == 0


def test_existing_random_filename_is_never_overwritten(client, paths, monkeypatch):
    filename = "a" * 32 + ".png"
    target = paths[1] / filename
    target.write_bytes(b"existing")

    def validated(images):
        return [uploads.ValidatedImageUpload(filename, "a.png", "image/png", image_bytes())]

    monkeypatch.setattr(public, "validate_image_uploads", validated)
    assert post_image(client, image_bytes()).status_code == 503
    assert target.read_bytes() == b"existing"
    assert list(paths[1].iterdir()) == [target]


@pytest.mark.parametrize(
    "error", [SyntaxError, EOFError, TypeError, OverflowError, struct.error, zlib.error]
)
def test_decoder_failures_are_form_errors(client, monkeypatch, error):
    def fail(*args, **kwargs):
        raise error("private decoder internals")

    monkeypatch.setattr(uploads.Image, "open", fail)
    response = post_image(client, image_bytes())
    assert response.status_code == 400
    assert "private decoder internals" not in response.text


def test_reencoded_size_and_animation_are_rejected(client, monkeypatch):
    data = image_bytes(optimize=True)
    _, normalized = uploads.normalize_image(data)
    assert len(normalized) > len(data)
    monkeypatch.setattr(uploads, "MAX_UPLOAD_SIZE_BYTES", len(data))
    assert post_image(client, data).status_code == 400
    monkeypatch.setattr(uploads, "MAX_UPLOAD_SIZE_BYTES", 100000)
    output = io.BytesIO()
    with Image.new("RGB", (10, 10), "red") as first, Image.new("RGB", (10, 10), "blue") as second:
        first.save(output, "PNG", save_all=True, append_images=[second])
    assert post_image(client, output.getvalue()).status_code == 400


def test_unreadable_temporary_upload_returns_unavailable(client, monkeypatch):
    def fail(images):
        raise OSError("private filesystem detail")

    monkeypatch.setattr(public, "validate_image_uploads", fail)
    response = post_image(client, image_bytes())
    assert response.status_code == 503
    assert "private filesystem" not in response.text


def test_upload_storage_quota_is_atomic_under_concurrency(client, paths, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    data = image_bytes()
    monkeypatch.setattr(public, "MAX_UPLOAD_STORAGE_BYTES", len(uploads.normalize_image(data)[1]))
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda _: post_image(client, data).status_code, range(2)))
    assert sorted(codes) == [303, 400]
    assert len(list(paths[1].iterdir())) == 1
    with db.db_connect() as conn:
        assert conn.execute("SELECT count(*) FROM usage_sessions").fetchone()[0] == 1
