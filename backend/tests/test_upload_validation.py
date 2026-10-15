from __future__ import annotations

import io

from PIL import Image

from .conftest import ANALYZE_FORM, HEADERS, analyze_files


def post(client, data, **kw):
    form = {**ANALYZE_FORM, **kw.pop("form", {})}
    return client.post("/api/v1/analyze", headers=HEADERS, files=analyze_files(data, **kw), data=form)


def test_valid_jpeg_accepted(client, jpeg_bytes):
    r = post(client, jpeg_bytes())
    assert r.status_code == 200, r.text
    assert r.json()["model_kind"] == "mock"


def test_text_file_rejected_as_bad_type(client):
    r = post(client, b"just some text, definitely not an image", filename="note.txt", content_type="text/plain")
    assert r.status_code == 415


def test_pdf_with_image_extension_rejected(client):
    r = post(client, b"%PDF-1.7\n%fake", filename="holiday.jpg", content_type="image/jpeg")
    assert r.status_code == 415


def test_spoofed_extension_png_named_txt_is_accepted_by_content(client):
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (1, 2, 3)).save(buf, format="PNG")
    r = post(client, buf.getvalue(), filename="notes.txt", content_type="text/plain")
    assert r.status_code == 200  # type comes from magic bytes, not the name or Content-Type


def test_gif_not_supported_even_with_jpg_name(client):
    buf = io.BytesIO()
    Image.new("P", (8, 8)).save(buf, format="GIF")
    r = post(client, buf.getvalue(), filename="a.jpg", content_type="image/jpeg")
    assert r.status_code == 415


def test_jpeg_magic_with_garbage_body_rejected(client):
    r = post(client, b"\xff\xd8\xff" + b"\x00" * 200)
    assert r.status_code == 400


def test_oversize_rejected(client):
    big = b"\xff\xd8\xff" + b"\x00" * 300_000
    assert post(client, big).status_code == 413


def test_oversize_rejected_early_by_content_length(client):
    r = client.post(
        "/api/v1/analyze",
        headers=HEADERS,
        files=analyze_files(b"\xff\xd8\xff" + b"\x00" * 1_300_000),
        data=ANALYZE_FORM,
    )
    assert r.status_code == 413


def test_pixel_bomb_rejected_before_decode(client):
    buf = io.BytesIO()
    Image.new("1", (3000, 3000), 0).save(buf, format="PNG")  # tiny file, 9M pixels > 1M limit
    assert len(buf.getvalue()) < 200_000
    r = post(client, buf.getvalue(), filename="bomb.png", content_type="image/png")
    assert r.status_code == 413
    assert "pixels" in r.json()["detail"]


def test_empty_upload_rejected(client):
    assert post(client, b"").status_code == 400


def test_rights_attestation_required(client, jpeg_bytes):
    assert post(client, jpeg_bytes(), form={"rights_attested": "false"}).status_code == 422
    r = client.post("/api/v1/analyze", headers=HEADERS, files=analyze_files(jpeg_bytes()), data={"model": "mock"})
    assert r.status_code == 422


def test_unknown_and_unavailable_models(client, jpeg_bytes):
    assert post(client, jpeg_bytes(), form={"model": "nope"}).status_code == 400
    r = post(client, jpeg_bytes(), form={"model": "geoclip-v1"})
    assert r.status_code == 503 and "unavailable" in r.json()["detail"]
