from __future__ import annotations

import hashlib

from .base import GeoResult, RawCandidate

# (lat, lon, country_code, name). Deterministic stand-ins; NOT predictions about the image.
_PLACES = [
    (30.2672, -97.7431, "US", "Austin"),
    (48.8566, 2.3522, "FR", "Paris"),
    (35.6762, 139.6503, "JP", "Tokyo"),
    (-33.8688, 151.2093, "AU", "Sydney"),
    (-22.9068, -43.1729, "BR", "Rio de Janeiro"),
    (64.1466, -21.9426, "IS", "Reykjavik"),
    (-1.2921, 36.8219, "KE", "Nairobi"),
    (28.6139, 77.2090, "IN", "New Delhi"),
    (55.7558, 37.6173, "RU", "Moscow"),
    (40.7128, -74.0060, "US", "New York"),
    (-34.6037, -58.3816, "AR", "Buenos Aires"),
    (59.9139, 10.7522, "NO", "Oslo"),
]


class MockGeoAdapter:
    """Deterministic on the image hash. Always reports kind='mock'; the output is not a real prediction."""

    id = "mock"
    version = "mock-0.1"
    kind = "mock"

    def availability(self) -> tuple[bool, str | None]:
        return True, None

    def predict(self, image_bytes: bytes, *, image_sha256: str, top_k: int = 5) -> GeoResult:
        digest = hashlib.sha256(image_sha256.encode()).digest()
        start = digest[0] % len(_PLACES)
        step = (1, 5, 7, 11)[digest[1] % 4]  # coprime with 12 places, so the stride never repeats
        order = [(start + k * step) % len(_PLACES) for k in range(min(top_k, len(_PLACES)))]
        top = 0.30 + (digest[2] / 255.0) * 0.45  # 0.30..0.75
        out = []
        for rank, idx in enumerate(order):
            lat, lon, cc, name = _PLACES[idx]
            out.append(
                RawCandidate(lat=lat, lon=lon, score=round(top * (0.6**rank), 4), label=f"MOCK: {name}", country_code=cc)
            )
        return GeoResult(candidates=out, latency_ms=0.0)


class UnavailableGeoAdapter:
    """Placeholder for a registered model whose runtime is not installed/configured."""

    kind = "real"

    def __init__(self, adapter_id: str, version: str, reason: str):
        self.id = adapter_id
        self.version = version
        self._reason = reason

    def availability(self) -> tuple[bool, str | None]:
        return False, self._reason

    def predict(self, image_bytes: bytes, *, image_sha256: str, top_k: int = 5) -> GeoResult:
        raise RuntimeError(f"{self.id} is unavailable: {self._reason}")


class UnavailableClueAdapter:
    kind = "real"

    def __init__(self, adapter_id: str, version: str, reason: str):
        self.id = adapter_id
        self.version = version
        self._reason = reason

    def availability(self) -> tuple[bool, str | None]:
        return False, self._reason

    def extract(self, image_bytes: bytes, *, mime: str):
        raise RuntimeError(f"{self.id} is unavailable: {self._reason}")
