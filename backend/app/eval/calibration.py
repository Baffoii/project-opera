from __future__ import annotations

from .metrics import HIT_KM, ItemResult, percentile

MIN_BAND_ITEMS = 5
HIGH_HIT_RATE = 0.8
MEDIUM_HIT_RATE = 0.5
ABSTAIN_MISS_KM = 750


def _cutoff(ranked: list[ItemResult], target: float) -> float | None:
    """Lowest score such that the items scoring at or above it have a top-1 hit rate >= target, with at
    least MIN_BAND_ITEMS items. Scanning from the largest set down keeps the band as wide as the data allow."""
    for k in range(len(ranked), MIN_BAND_ITEMS - 1, -1):
        top = ranked[:k]
        if sum(i.error_km <= HIT_KM for i in top) / k >= target:
            return ranked[k - 1].top1_score
    return None


def calibrate(items: list[ItemResult]) -> dict:
    """Derive confidence-band and abstention thresholds from one set of results (the seed split).
    The output is a lookup rule over raw model scores, not a probability model: candidates stay uncalibrated."""
    usable = [i for i in items if not i.failed and i.error_km is not None and i.top1_score is not None]
    ranked = sorted(usable, key=lambda i: i.top1_score, reverse=True)
    high = _cutoff(ranked, HIGH_HIT_RATE)
    medium = _cutoff(ranked, MEDIUM_HIT_RATE)
    if medium is not None and high is not None:
        medium = min(medium, high)
    within = [i for i in usable if i.error_km <= ABSTAIN_MISS_KM]
    abstain = min(i.top1_score for i in within) if within else None
    if abstain is not None and medium is not None:
        abstain = min(abstain, medium)  # never abstain inside a band that is reported as medium or high

    def band_errors(lo: float | None, hi: float | None) -> list[float]:
        return [i.error_km for i in usable if (lo is None or i.top1_score >= lo) and (hi is None or i.top1_score < hi)]

    groups = {
        "high": band_errors(high, None) if high is not None else [],
        "medium": band_errors(medium, high) if medium is not None else [],
        "low": band_errors(None, medium if medium is not None else None),
    }
    uncertainty = {
        band: (round(percentile(errors, 80), 1) if len(errors) >= MIN_BAND_ITEMS else None)
        for band, errors in groups.items()
    }
    return {
        "n": len(usable),
        "thresholds": {
            "band_high_at": high,
            "band_medium_at": medium,
            "abstain_below_score": abstain,
        },
        "uncertainty_km_p80": uncertainty,
        "band_sizes": {band: len(errors) for band, errors in groups.items()},
        "rule": (
            f"high = lowest score whose cumulative top-1 hit rate within {HIT_KM} km is >= {HIGH_HIT_RATE} "
            f"(n >= {MIN_BAND_ITEMS}); medium likewise at {MEDIUM_HIT_RATE}; abstain below the lowest score of "
            f"any item within {ABSTAIN_MISS_KM} km; uncertainty = p80 error of the band when it holds >= "
            f"{MIN_BAND_ITEMS} items. A None means the data were too thin to set it."
        ),
    }
