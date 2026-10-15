from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field

from ..geo.haversine import haversine_km

THRESHOLDS_KM = (1, 25, 200, 750)
BANDS = ("high", "medium", "low")
HIT_KM = 200  # a "hit" for calibration tables: top-1 within 200 km (region level)
SLICE_KEYS = ("country", "continent", "settlement_type", "landscape", "image_source_type")
GEOGUESSR_SCALE_KM = 1492.7


@dataclass
class ItemResult:
    """One evaluated image. `error_km` is None when the model failed or returned nothing."""

    image_id: str
    truth_lat: float
    truth_lon: float
    top1_lat: float | None = None
    top1_lon: float | None = None
    error_km: float | None = None
    top5_errors_km: list[float] = field(default_factory=list)
    top1_score: float | None = None
    band: str | None = None
    abstained: bool = False
    failed: bool = False
    truth_country: str | None = None
    top1_country: str | None = None
    top5_countries: list[str | None] = field(default_factory=list)
    latency_ms: float | None = None
    cost_usd: float | None = None
    slices: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def great_circle_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return haversine_km(lat1, lon1, lat2, lon2)


def geoguessr_style_score(distance_km: float) -> int:
    """5000 * exp(-d / 1492.7), the commonly cited world-map GeoGuessr curve. A game score, not a model metric."""
    return round(5000 * math.exp(-max(0.0, distance_km) / GEOGUESSR_SCALE_KM))


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile (q in 0..100). Deterministic and dependency-free."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _rounded(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def _rate(hits: int, n: int) -> float | None:
    return round(hits / n, 4) if n else None


def accuracy_block(items: list[ItemResult]) -> dict:
    """Distance and threshold metrics over the items that produced a top-1."""
    scored = [i for i in items if i.error_km is not None]
    errors = [i.error_km for i in scored]
    block: dict = {
        "n": len(scored),
        "median_km": _rounded(_median(errors), 2),
        "mean_km": _rounded(_mean(errors), 2),
        "within_km": {str(t): _rate(sum(e <= t for e in errors), len(errors)) for t in THRESHOLDS_KM},
        "top5_within_km": {
            str(t): _rate(sum(any(e <= t for e in i.top5_errors_km) for i in scored), len(scored))
            for t in THRESHOLDS_KM
        },
    }
    with_country = [i for i in scored if i.truth_country and i.top1_country is not None]
    block["country_accuracy"] = _rate(sum(i.top1_country == i.truth_country for i in with_country), len(with_country))
    block["country_n"] = len(with_country)
    block["top5_country_recall"] = _rate(
        sum(i.truth_country in i.top5_countries for i in with_country), len(with_country)
    )
    return block


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def reliability_table(items: list[ItemResult], hit_km: float = HIT_KM) -> list[dict]:
    """Observed top-1 hit rate per confidence band. Abstained items are reported separately."""
    rows = []
    for band in BANDS:
        members = [i for i in items if i.band == band and not i.abstained and i.error_km is not None]
        hits = sum(i.error_km <= hit_km for i in members)
        rows.append({"band": band, "n": len(members), "hits": hits, "hit_rate": _rate(hits, len(members)), "hit_km": hit_km})
    return rows


def summarize(items: list[ItemResult]) -> dict:
    """Metrics for one group of items. `all` ignores abstention (what the raw model said);
    `answered` keeps only items the abstention rule let through."""
    failed = [i for i in items if i.failed]
    ok = [i for i in items if not i.failed]
    answered = [i for i in ok if not i.abstained]
    latencies = [i.latency_ms for i in ok if i.latency_ms is not None]
    costs = [i.cost_usd for i in ok if i.cost_usd is not None]
    return {
        "n_items": len(items),
        "n_failed": len(failed),
        "all": accuracy_block(ok),
        "answered": accuracy_block(answered),
        "abstention_rate": _rate(sum(i.abstained for i in ok), len(ok)),
        "reliability": reliability_table(ok),
        "ops": {
            "latency_p50_ms": _rounded(percentile(latencies, 50), 1),
            "latency_p95_ms": _rounded(percentile(latencies, 95), 1),
            "cost_per_request_usd": _rounded(_mean(costs), 6),
            "cost_total_usd": _rounded(sum(costs), 6) if costs else None,
        },
    }


def slice_metrics(items: list[ItemResult], keys: Iterable[str] = SLICE_KEYS) -> dict[str, dict[str, dict]]:
    """Per-slice summaries. Slices with fewer than 1 item are never emitted; sizes are in `n_items`."""
    out: dict[str, dict[str, dict]] = {}
    for key in keys:
        groups: dict[str, list[ItemResult]] = defaultdict(list)
        for item in items:
            value = item.slices.get(key)
            if value:
                groups[value].append(item)
        out[key] = {value: _slice_summary(group) for value, group in sorted(groups.items())}
    return out


def _slice_summary(items: list[ItemResult]) -> dict:
    block = summarize(items)
    return {
        "n_items": block["n_items"],
        "n_failed": block["n_failed"],
        "median_km": block["all"]["median_km"],
        "within_km": block["all"]["within_km"],
        "country_accuracy": block["all"]["country_accuracy"],
        "abstention_rate": block["abstention_rate"],
    }
