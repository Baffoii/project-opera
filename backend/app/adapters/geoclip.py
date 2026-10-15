from __future__ import annotations

import importlib.metadata
import importlib.util
import io
import logging
import os
import threading
import time

from ..config import Settings
from ..geo.haversine import haversine_km
from .base import GeoResult, RawCandidate

log = logging.getLogger("opera.geoclip")


class GeoClipAdapter:
    """GeoCLIP (VicenteVivan/geo-clip) pretrained image->GPS baseline, run locally on CPU or GPU.

    The model scores a fixed gallery of ~100K GPS points. `score` is the raw softmax mass of one gallery
    point: it is NOT a calibrated probability and is never averaged with any other model's output.
    """

    id = "geoclip-v1"
    kind = "real"

    def __init__(self, settings: Settings):
        self.settings = settings
        try:
            pkg = importlib.metadata.version("geoclip")
        except importlib.metadata.PackageNotFoundError:
            pkg = "not-installed"
        self.version = f"geoclip-{pkg}"
        self._model = None
        self._lock = threading.Lock()
        self.last_load_ms: float | None = None

    def availability(self) -> tuple[bool, str | None]:
        for module in ("torch", "transformers", "geoclip"):
            if importlib.util.find_spec(module) is None:
                return False, f"'{module}' is not installed (pip install -e 'backend[geoclip]')"
        return True, None

    def _ensure_loaded(self) -> float:
        """Load on first use (weights come from the wheel; the CLIP backbone downloads into model_cache_dir)."""
        if self._model is not None:
            return 0.0
        started = time.perf_counter()
        os.environ.setdefault("HF_HOME", str(self.settings.model_cache_dir))
        from geoclip import GeoCLIP  # heavy import, deliberately lazy

        model = GeoCLIP()
        model.eval()
        self._model = model
        self.last_load_ms = (time.perf_counter() - started) * 1000
        log.info("GeoCLIP loaded in %.0f ms", self.last_load_ms)
        return self.last_load_ms

    def predict(self, image_bytes: bytes, *, image_sha256: str, top_k: int = 5) -> GeoResult:
        started = time.perf_counter()
        with self._lock:
            load_ms = self._ensure_loaded()
            pool = max(top_k, self.settings.geoclip_pool)
            infer_start = time.perf_counter()
            gps, scores = self._model.predict(io.BytesIO(image_bytes), top_k=pool)
            infer_ms = (time.perf_counter() - infer_start) * 1000
        points = [(float(a), float(b), float(c)) for (a, b), c in zip(gps.tolist(), scores.tolist())]
        kept = suppress_nearby(points, top_k, self.settings.geoclip_nms_km)
        stages = {"model_infer": infer_ms}
        if load_ms:
            stages["model_load"] = load_ms
        return GeoResult(
            candidates=[RawCandidate(lat=lat, lon=lon, score=score) for lat, lon, score in kept],
            latency_ms=(time.perf_counter() - started) * 1000,
            stages=stages,
            notes={"nms_km": self.settings.geoclip_nms_km, "gallery_pool": pool, "score": "raw gallery softmax mass"},
        )


def suppress_nearby(points: list[tuple[float, float, float]], top_k: int, min_km: float) -> list[tuple[float, float, float]]:
    """Greedy non-maximum suppression over (lat, lon, score) sorted by score. Scores are left untouched."""
    kept: list[tuple[float, float, float]] = []
    for lat, lon, score in sorted(points, key=lambda p: p[2], reverse=True):
        if all(haversine_km(lat, lon, k[0], k[1]) >= min_km for k in kept):
            kept.append((lat, lon, score))
            if len(kept) == top_k:
                break
    return kept
