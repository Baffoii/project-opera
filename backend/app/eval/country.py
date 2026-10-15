from __future__ import annotations

import importlib.util
import threading
from typing import Protocol


class CountryResolver(Protocol):
    id: str

    def resolve(self, points: list[tuple[float, float]]) -> list[str | None]:
        """ISO 3166-1 alpha-2 code per (lat, lon), or None when it cannot be determined."""
        ...


class OfflineCountryResolver:
    """Nearest GeoNames city (>=1000 people) via the `reverse_geocoder` package, fully offline.

    This is an approximation: a point on open water or near a border resolves to the nearest city's country,
    so country accuracy near borders and coasts can be off by one. It exists so evaluation never needs a
    network call per prediction.
    """

    id = "offline-nearest-city"

    def __init__(self) -> None:
        self._lock = threading.Lock()

    @staticmethod
    def available() -> bool:
        return importlib.util.find_spec("reverse_geocoder") is not None

    def resolve(self, points: list[tuple[float, float]]) -> list[str | None]:
        if not points:
            return []
        import reverse_geocoder  # lazy: loads a ~30 MB index

        with self._lock:
            hits = reverse_geocoder.search(list(points), mode=1)  # mode=1: no multiprocessing
        return [str(h["cc"]).upper() if h.get("cc") else None for h in hits]


def default_country_resolver() -> CountryResolver | None:
    return OfflineCountryResolver() if OfflineCountryResolver.available() else None
