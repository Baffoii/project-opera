from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

import imagehash
from PIL import Image, ImageOps, UnidentifiedImageError


class UploadError(Exception):
    """Raised for client-correctable upload problems. `status` is the HTTP status to answer with."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class SanitizedImage:
    data: bytes  # re-encoded pixels only: no EXIF / XMP / IPTC / ICC / text chunks
    mime: str
    width: int
    height: int
    sha256: str
    phash: str


_MIME_TO_PIL = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


def sniff_mime(data: bytes) -> str | None:
    """Identify the image type from magic bytes. The client's filename and Content-Type are never trusted."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def sanitize_image(data: bytes, *, max_bytes: int, max_pixels: int) -> SanitizedImage:
    if not data:
        raise UploadError(400, "Empty upload.")
    if len(data) > max_bytes:
        raise UploadError(413, f"Image is larger than the {max_bytes // (1024 * 1024)} MB limit.")
    mime = sniff_mime(data)
    if mime is None:
        raise UploadError(415, "Unsupported image type. Use JPEG, PNG or WebP.")

    try:
        # Image.open is lazy: it reads the header only, so the pixel-count check happens before decoding.
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format != _MIME_TO_PIL[mime]:
                raise UploadError(415, "File content does not match its image type.")
            width, height = probe.size
            if width < 1 or height < 1 or width * height > max_pixels:
                raise UploadError(413, "Image has too many pixels.")
            if getattr(probe, "n_frames", 1) > 1:
                probe.seek(0)  # animated input: only the first frame is kept
            probe.load()
            # Apply the EXIF orientation first so removing metadata does not rotate the picture.
            oriented = ImageOps.exif_transpose(probe)
            if oriented.mode not in ("RGB", "L"):
                has_alpha = "A" in oriented.mode or "transparency" in oriented.info
                oriented = oriented.convert("RGBA" if has_alpha and mime != "image/jpeg" else "RGB")
            # A fresh image carries over pixels only; `info` (EXIF/XMP/ICC/text chunks) is not copied.
            clean = Image.new(oriented.mode, oriented.size)
            clean.paste(oriented)
    except UploadError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise UploadError(413, "Image has too many pixels.") from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise UploadError(400, "The image could not be decoded.") from None

    out = io.BytesIO()
    fmt = _MIME_TO_PIL[mime]
    if fmt == "JPEG":
        clean.save(out, format="JPEG", quality=90, optimize=True)
    elif fmt == "PNG":
        clean.save(out, format="PNG", optimize=True)
    else:
        clean.save(out, format="WEBP", quality=90)
    encoded = out.getvalue()
    return SanitizedImage(
        data=encoded,
        mime=mime,
        width=clean.width,
        height=clean.height,
        sha256=hashlib.sha256(encoded).hexdigest(),
        phash=str(imagehash.phash(clean.convert("RGB"))),
    )
