"""Download the images of a benchmark dataset listed in its manifest, one polite request at a time.

    python scripts/fetch_benchmark.py opera-commons-v1

Each file is checked against the manifest `sha256`; a mismatch is deleted and reported, never kept. Images are
git-ignored. Set OPERA_CONTEXT_USER_AGENT to a real app name plus contact URL (Wikimedia's User-Agent policy).
"""
from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.eval.dataset import DatasetError, load_dataset  # noqa: E402

PAUSE_S = 2.0
MAX_ATTEMPTS = 5


def fetch(url: str, client: httpx.Client) -> bytes | None:
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = client.get(url)
        except httpx.HTTPError:
            response = None
        if response is not None and response.status_code == 200:
            return response.content
        wait = 10.0 * (attempt + 1) if response is not None and response.status_code == 429 else 3.0 * (attempt + 1)
        time.sleep(wait)
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    settings = get_settings()
    try:
        dataset = load_dataset(settings.benchmark_dir, argv[1])
    except DatasetError as exc:
        print(f"error: {exc}")
        return 1
    images = dataset.root / "images"
    images.mkdir(exist_ok=True)
    bad = fetched = present = 0
    with httpx.Client(headers={"User-Agent": settings.context_user_agent}, timeout=30, follow_redirects=True) as client:
        for item in dataset.items:
            target = dataset.image_path(item)
            if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == item.sha256:
                present += 1
                continue
            if not item.image_url:
                print(f"skip {item.image_id}: no image_url in the manifest")
                bad += 1
                continue
            data = fetch(item.image_url, client)
            if data is None or hashlib.sha256(data).hexdigest() != item.sha256:
                print(f"FAILED {item.image_id}: download failed or hash differs from the manifest")
                bad += 1
            else:
                target.write_bytes(data)
                fetched += 1
            time.sleep(PAUSE_S)
    print(f"{dataset.id}: {present} already present, {fetched} downloaded, {bad} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
