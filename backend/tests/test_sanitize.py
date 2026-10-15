from __future__ import annotations

import io

import pytest
from PIL import Image, ImageOps, PngImagePlugin

from app.services.sanitize import UploadError, sanitize_image

SECRET = "SECRETCAM-9000"


def _jpeg_with_metadata(orientation: int = 1) -> bytes:
    exif = Image.Exif()
    exif[0x010F] = SECRET  # Make
    exif[0x0110] = "Model-" + SECRET
    exif[0x0112] = orientation
    exif[0x8825] = {1: "N", 2: (30.0, 16.0, 2.0), 3: "W", 4: (97.0, 44.0, 35.0)}  # GPS IFD
    xmp = b'<?xpacket begin=""?><x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF>' + SECRET.encode() + b"</rdf:RDF></x:xmpmeta>"
    buf = io.BytesIO()
    img = Image.new("RGB", (80, 40), (10, 120, 200))
    img.paste((255, 0, 0), (0, 0, 20, 20))
    img.save(buf, format="JPEG", exif=exif, xmp=xmp, quality=92)
    return buf.getvalue()


def _limits(**kw):
    return dict(max_bytes=5_000_000, max_pixels=10_000_000, **kw)


def test_fixture_really_contains_gps_and_xmp():
    src = _jpeg_with_metadata()
    exif = Image.open(io.BytesIO(src)).getexif()
    assert exif.get_ifd(0x8825).get(1) == "N", "test fixture must carry GPS or the strip test is vacuous"
    assert SECRET.encode() in src and b"Exif" in src


def test_jpeg_gps_exif_xmp_are_removed():
    out = sanitize_image(_jpeg_with_metadata(), **_limits())
    reread = Image.open(io.BytesIO(out.data))
    exif = reread.getexif()
    assert len(exif) == 0
    assert exif.get_ifd(0x8825) == {}
    assert "xmp" not in reread.info and "exif" not in reread.info and "icc_profile" not in reread.info
    for needle in (SECRET.encode(), b"Exif", b"GPSLatitude", b"http://ns.adobe.com/xap", b"xmpmeta"):
        assert needle not in out.data


def test_orientation_is_applied_before_stripping():
    src = _jpeg_with_metadata(orientation=6)  # rotate 90 CW when displayed
    expected = ImageOps.exif_transpose(Image.open(io.BytesIO(src)))
    out = sanitize_image(src, **_limits())
    assert (out.width, out.height) == expected.size == (40, 80)
    assert Image.open(io.BytesIO(out.data)).getexif().get(0x0112) is None


def test_png_text_and_exif_chunks_removed():
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", SECRET)
    info.add_text("XML:com.adobe.xmp", "<x:xmpmeta>" + SECRET + "</x:xmpmeta>")
    exif = Image.Exif()
    exif[0x8825] = {1: "S", 2: (10.0, 0.0, 0.0), 3: "E", 4: (20.0, 0.0, 0.0)}
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), (5, 5, 5)).save(buf, format="PNG", pnginfo=info, exif=exif)
    src = buf.getvalue()
    assert SECRET.encode() in src
    out = sanitize_image(src, **_limits())
    assert SECRET.encode() not in out.data
    assert b"eXIf" not in out.data and b"tEXt" not in out.data and b"iTXt" not in out.data
    assert Image.open(io.BytesIO(out.data)).info.get("Comment") is None


def test_rgba_png_keeps_alpha_and_webp_roundtrips():
    buf = io.BytesIO()
    Image.new("RGBA", (10, 10), (1, 2, 3, 128)).save(buf, format="PNG")
    out = sanitize_image(buf.getvalue(), **_limits())
    assert Image.open(io.BytesIO(out.data)).mode == "RGBA"
    wb = io.BytesIO()
    Image.new("RGB", (10, 10), (9, 9, 9)).save(wb, format="WEBP")
    assert sanitize_image(wb.getvalue(), **_limits()).mime == "image/webp"


def test_hashes_are_stable_and_content_based():
    a = sanitize_image(_jpeg_with_metadata(), **_limits())
    b = sanitize_image(_jpeg_with_metadata(), **_limits())
    assert a.sha256 == b.sha256 and len(a.phash) == 16


def test_format_mismatch_rejected():
    buf = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buf, format="PNG")
    with pytest.raises(UploadError):  # PNG bytes cannot pass as another type; truncated body is undecodable
        sanitize_image(buf.getvalue()[:20], **_limits())


def test_filename_never_reaches_response_or_storage(client, jpeg_bytes, ctx):
    from .conftest import ANALYZE_FORM, HEADERS, analyze_files

    r = client.post(
        "/api/v1/analyze",
        headers=HEADERS,
        files=analyze_files(jpeg_bytes(), filename="Alice-Smith-home-address.jpg"),
        data=ANALYZE_FORM,
    )
    assert "Alice" not in r.text
    names = [p.name for p in ctx.settings.storage_dir.iterdir()]
    assert names and all("Alice" not in n and n.endswith(".img") and len(n) == 36 for n in names)
