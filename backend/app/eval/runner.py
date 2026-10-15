from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from ..adapters.base import ClueAdapter, GeoAdapter
from ..config import Settings
from ..services.pipeline import band_for, decide_status
from ..services.sanitize import UploadError, sanitize_image
from .country import CountryResolver
from .dataset import BenchmarkItem, Dataset, DatasetError, read_verified
from .metrics import ItemResult, great_circle_km, slice_metrics, summarize

log = logging.getLogger("opera.eval")
EVAL_VERSION = "eval-1"


@dataclass
class EvalConfig:
    dataset: str
    dataset_version: str
    split: str
    model: str
    model_version: str
    model_kind: str
    use_vlm_clues: bool
    seed: int
    limit: int | None
    thresholds: dict
    country_resolver: str | None
    eval_version: str = EVAL_VERSION

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @property
    def hash(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()


@dataclass
class EvalOutcome:
    items: list[ItemResult]
    metrics: dict
    slices: dict
    notices: list[str] = field(default_factory=list)


def thresholds_from(settings: Settings) -> dict:
    return {
        "abstain_below_score": settings.abstain_below_score,
        "band_high_at": settings.band_high_at,
        "band_medium_at": settings.band_medium_at,
    }


def build_config(
    settings: Settings,
    dataset: Dataset,
    adapter: GeoAdapter,
    *,
    split: str,
    use_vlm_clues: bool,
    seed: int,
    limit: int | None,
    resolver: CountryResolver | None,
) -> EvalConfig:
    return EvalConfig(
        dataset=dataset.id,
        dataset_version=dataset.version,
        split=split,
        model=adapter.id,
        model_version=adapter.version,
        model_kind=adapter.kind,
        use_vlm_clues=use_vlm_clues,
        seed=seed,
        limit=limit,
        thresholds=thresholds_from(settings),
        country_resolver=resolver.id if resolver else None,
    )


def evaluate_item(
    settings: Settings,
    dataset: Dataset,
    item: BenchmarkItem,
    adapter: GeoAdapter,
    *,
    clue_adapter: ClueAdapter | None,
    resolver: CountryResolver | None,
    price: Callable[[int | None, int | None], float | None],
) -> ItemResult:
    result = ItemResult(
        image_id=item.image_id,
        truth_lat=item.lat,
        truth_lon=item.lon,
        truth_country=item.country or None,
        slices=item.slices(),
    )
    try:
        data = read_verified(dataset, item)
        image = sanitize_image(data, max_bytes=settings.max_upload_bytes, max_pixels=settings.max_image_pixels)
    except (DatasetError, UploadError) as exc:
        log.warning("eval item %s unusable: %s", item.image_id, exc)
        result.failed = True
        return result

    clue_abstain: str | None = None
    cost: float | None = None
    if clue_adapter is not None:
        try:
            clues = clue_adapter.extract(image.data, mime=image.mime)
            cost = price(clues.input_tokens, clues.output_tokens)
            if clues.abstain:
                clue_abstain = clues.abstain_reason or "no reason given"
        except Exception as exc:  # clue failures never fail the item; geolocation continues
            log.warning("eval clue step failed: %s", type(exc).__name__)

    started = time.perf_counter()
    try:
        geo = adapter.predict(image.data, image_sha256=image.sha256, top_k=5)
    except Exception as exc:
        log.warning("eval item %s: %s failed: %s", item.image_id, adapter.id, type(exc).__name__)
        result.failed = True
        return result
    elapsed_ms = (time.perf_counter() - started) * 1000 - geo.stages.get("model_load", 0.0)

    raw = sorted(geo.candidates, key=lambda c: c.score, reverse=True)[:5]
    status, _ = decide_status(
        raw, geo_error=None, clue_abstain=clue_abstain, abstain_below=settings.abstain_below_score
    )
    result.latency_ms = round(max(elapsed_ms, 0.0), 2)
    result.cost_usd = cost
    result.abstained = status == "abstained"
    if not raw:
        return result
    result.top1_lat, result.top1_lon, result.top1_score = raw[0].lat, raw[0].lon, raw[0].score
    result.top5_errors_km = [round(great_circle_km(item.lat, item.lon, c.lat, c.lon), 3) for c in raw]
    result.error_km = result.top5_errors_km[0]
    result.band = band_for(raw[0].score, settings.band_high_at, settings.band_medium_at)
    countries = [c.country_code for c in raw]
    if resolver is not None and any(c is None for c in countries):
        resolved = resolver.resolve([(c.lat, c.lon) for c in raw])
        countries = [given or found for given, found in zip(countries, resolved)]
    result.top5_countries = [c.upper() if c else None for c in countries]
    result.top1_country = result.top5_countries[0]
    return result


def strip_ops(block: dict) -> dict:
    """Latency and cost vary between machines; everything else must be identical across repeat runs."""
    return {k: (strip_ops(v) if isinstance(v, dict) else v) for k, v in block.items() if k != "ops"}


def compute_outcome(items: list[ItemResult], notices: list[str]) -> EvalOutcome:
    groups: dict[str, list[ItemResult]] = defaultdict(list)
    for item in items:
        groups[item.slices.get("image_source_type", "unknown")].append(item)
    metrics = {
        "overall": summarize(items),
        # Street-view-style and user-contributed-style photos are never pooled into one headline number.
        "by_image_source_type": {k: summarize(v) for k, v in sorted(groups.items())},
        "notices": notices,
    }
    slices = slice_metrics(items)
    reproducible = {"overall": strip_ops(metrics["overall"]), "by_source": {k: strip_ops(v) for k, v in metrics["by_image_source_type"].items()}, "slices": slices}
    metrics["reproducible_hash"] = hashlib.sha256(json.dumps(reproducible, sort_keys=True).encode()).hexdigest()
    return EvalOutcome(items=items, metrics=metrics, slices=slices, notices=notices)
