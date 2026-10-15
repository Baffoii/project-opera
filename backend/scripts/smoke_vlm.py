"""Live check of the VLM clue adapter. Run after adding OPENAI_API_KEY to .env and restarting the backend.

    backend/.venv/bin/python backend/scripts/smoke_vlm.py [optional-image-path]

With no argument it renders a synthetic road scene (no real photo, no people). The key is never printed.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from PIL import Image, ImageDraw  # noqa: E402

from app.adapters.vlm_clues import VlmClueAdapter  # noqa: E402
from app.config import Settings  # noqa: E402
from app.services.sanitize import sanitize_image  # noqa: E402


def synthetic_scene() -> bytes:
    img = Image.new("RGB", (1024, 640), (150, 195, 235))
    d = ImageDraw.Draw(img)
    d.polygon([(0, 330), (260, 190), (520, 300), (800, 170), (1024, 320), (1024, 400), (0, 400)], fill=(70, 110, 80))
    d.rectangle([0, 400, 1024, 640], fill=(70, 70, 74))
    for x in range(40, 1024, 160):
        d.rectangle([x, 520, x + 80, 534], fill=(235, 235, 235))
    d.rectangle([700, 330, 710, 470], fill=(90, 90, 90))
    d.rectangle([620, 300, 790, 345], fill=(20, 90, 160))
    d.text((640, 315), "LISBOA 12 km", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def main() -> int:
    settings = Settings()
    adapter = VlmClueAdapter(settings)
    ready, reason = adapter.availability()
    if not ready:
        print(f"vlm-clues unavailable: {reason}")
        if reason == "no key":
            print("Add OPENAI_API_KEY to .env (repo root), then re-run.")
        return 2

    raw = Path(sys.argv[1]).read_bytes() if len(sys.argv) > 1 else synthetic_scene()
    clean = sanitize_image(raw, max_bytes=settings.max_upload_bytes, max_pixels=settings.max_image_pixels)
    print(f"model: {adapter.model}   image: {clean.width}x{clean.height} {clean.mime} (EXIF stripped)")
    try:
        result = adapter.extract(clean.data, mime=clean.mime)
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return 1

    print(f"prompt: {result.prompt_version}   latency: {result.latency_ms:.0f} ms")
    if result.abstain:
        print(f"model abstained: {result.abstain_reason}")
    for note in result.notices:
        print(f"notice: {note}")
    for clue in result.clues:
        print(f"  [{clue['certainty']:11}] {clue['category']:12} {clue['text']}")
    print(f"region guesses (clue-model hints, not candidates): {result.region_guesses}")
    print(f"tokens: in={result.input_tokens} out={result.output_tokens}")
    if result.input_tokens is not None and result.output_tokens is not None:
        cost = (
            result.input_tokens / 1e6 * settings.vlm_price_input_per_mtok
            + result.output_tokens / 1e6 * settings.vlm_price_output_per_mtok
        )
        print(f"estimated cost: ${cost:.6f} (prices from OPERA_VLM_PRICE_* config)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
