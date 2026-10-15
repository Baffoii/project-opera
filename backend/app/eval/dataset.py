from __future__ import annotations

import csv
import hashlib
import io
import random
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import imagehash
from PIL import Image

MANIFEST_COLUMNS = (
    "image_id",
    "source_url",
    "license",
    "author",
    "lat",
    "lon",
    "country",
    "settlement_type",
    "landscape",
    "image_source_type",
)
# OPERA additions to the spec's columns.
EXTRA_COLUMNS = ("split", "continent", "filename", "image_url", "sha256")
SPLITS = ("seed", "heldout")
PHASH_MAX_DISTANCE = 6  # Hamming distance out of 64 bits; at or below this two images are near-duplicates


class DatasetError(Exception):
    """The dataset is missing, malformed or its images do not match the manifest. Message is safe to show."""


class LeakageError(DatasetError):
    """Images are shared between the seed and heldout splits."""

    def __init__(self, findings: list[dict]):
        self.findings = findings
        shown = "; ".join(f"{f['a']} ~ {f['b']} ({f['kind']})" for f in findings[:5])
        super().__init__(f"Leakage between splits: {len(findings)} duplicate pair(s): {shown}")


@dataclass(frozen=True)
class BenchmarkItem:
    image_id: str
    split: str
    lat: float
    lon: float
    country: str
    continent: str
    settlement_type: str
    landscape: str
    image_source_type: str
    license: str
    author: str
    source_url: str
    filename: str
    image_url: str
    sha256: str

    def slices(self) -> dict[str, str]:
        return {
            "country": self.country,
            "continent": self.continent,
            "settlement_type": self.settlement_type,
            "landscape": self.landscape,
            "image_source_type": self.image_source_type,
        }


@dataclass(frozen=True)
class Dataset:
    id: str
    root: Path
    version: str
    items: tuple[BenchmarkItem, ...]

    def image_path(self, item: BenchmarkItem) -> Path:
        return self.root / "images" / item.filename

    def select(self, split: str, *, seed: int = 0, limit: int | None = None) -> list[BenchmarkItem]:
        """Deterministic: sorted by id, optionally a seeded random subset (still returned sorted)."""
        if split not in (*SPLITS, "all"):
            raise DatasetError(f"Unknown split '{split}'. Use seed, heldout or all.")
        chosen = sorted((i for i in self.items if split == "all" or i.split == split), key=lambda i: i.image_id)
        if limit is not None and 0 < limit < len(chosen):
            chosen = sorted(random.Random(seed).sample(chosen, limit), key=lambda i: i.image_id)
        return chosen


def list_dataset_ids(benchmark_dir: Path) -> list[str]:
    root = Path(benchmark_dir)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if (p / "manifest.csv").is_file())


def load_dataset(benchmark_dir: Path, dataset_id: str) -> Dataset:
    if not dataset_id or "/" in dataset_id or "\\" in dataset_id or dataset_id.startswith("."):
        raise DatasetError("Invalid dataset id.")
    root = Path(benchmark_dir) / dataset_id
    manifest = root / "manifest.csv"
    if not manifest.is_file():
        raise DatasetError(f"Dataset '{dataset_id}' was not found.")
    raw = manifest.read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    missing = [c for c in (*MANIFEST_COLUMNS, *EXTRA_COLUMNS) if c not in (reader.fieldnames or [])]
    if missing:
        raise DatasetError(f"Manifest is missing columns: {', '.join(missing)}.")
    items: list[BenchmarkItem] = []
    seen: set[str] = set()
    for line, row in enumerate(reader, start=2):
        try:
            item = BenchmarkItem(
                image_id=row["image_id"].strip(),
                split=row["split"].strip(),
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                country=row["country"].strip(),
                continent=row["continent"].strip(),
                settlement_type=row["settlement_type"].strip(),
                landscape=row["landscape"].strip(),
                image_source_type=row["image_source_type"].strip(),
                license=row["license"].strip(),
                author=row["author"].strip(),
                source_url=row["source_url"].strip(),
                filename=row["filename"].strip(),
                image_url=row["image_url"].strip(),
                sha256=row["sha256"].strip().lower(),
            )
        except (ValueError, KeyError):
            raise DatasetError(f"Manifest line {line} is malformed.") from None
        if not item.image_id or item.image_id in seen:
            raise DatasetError(f"Manifest line {line} has an empty or duplicate image_id.")
        if item.split not in SPLITS:
            raise DatasetError(f"Manifest line {line}: split must be one of {', '.join(SPLITS)}.")
        if not (-90 <= item.lat <= 90 and -180 <= item.lon <= 180):
            raise DatasetError(f"Manifest line {line}: coordinates out of range.")
        if "/" in item.filename or "\\" in item.filename or item.filename.startswith("."):
            raise DatasetError(f"Manifest line {line}: unsafe filename.")
        seen.add(item.image_id)
        items.append(item)
    if not items:
        raise DatasetError(f"Dataset '{dataset_id}' has no items.")
    return Dataset(id=dataset_id, root=root, version=hashlib.sha256(raw).hexdigest()[:12], items=tuple(items))


def read_verified(dataset: Dataset, item: BenchmarkItem) -> bytes:
    """Image bytes, checked against the manifest hash so a silently changed file cannot skew a run."""
    path = dataset.image_path(item)
    if not path.is_file():
        raise DatasetError(
            f"Image '{item.image_id}' is not present locally. Run `python scripts/fetch_benchmark.py {dataset.id}`."
        )
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != item.sha256:
        raise DatasetError(f"Image '{item.image_id}' does not match the manifest hash; refusing to evaluate.")
    return data


def _phash(data: bytes) -> imagehash.ImageHash:
    with Image.open(io.BytesIO(data)) as img:
        return imagehash.phash(img.convert("RGB"))


def find_leakage(
    items: list[BenchmarkItem], read: Callable[[BenchmarkItem], bytes], *, max_distance: int = PHASH_MAX_DISTANCE
) -> list[dict]:
    """Exact (sha256 of the file) and near (perceptual hash) duplicates between different splits.
    Duplicates inside one split are allowed; only cross-split sharing invalidates a held-out test."""
    hashed = []
    for item in items:
        data = read(item)
        hashed.append((item, hashlib.sha256(data).hexdigest(), _phash(data)))
    findings: list[dict] = []
    for idx, (a, sha_a, ph_a) in enumerate(hashed):
        for b, sha_b, ph_b in hashed[idx + 1 :]:
            if a.split == b.split:
                continue
            if sha_a == sha_b:
                findings.append({"a": a.image_id, "b": b.image_id, "kind": "sha256", "distance": 0})
            elif (distance := ph_a - ph_b) <= max_distance:
                findings.append({"a": a.image_id, "b": b.image_id, "kind": "phash", "distance": int(distance)})
    return findings


def check_leakage(dataset: Dataset) -> None:
    findings = find_leakage(list(dataset.items), lambda item: read_verified(dataset, item))
    if findings:
        raise LeakageError(findings)
