from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import httpx

from ..config import Settings

log = logging.getLogger("opera.context")

ATTRIBUTION = "© OpenStreetMap contributors"
_PLACE_KEYS = ("city", "town", "village", "municipality", "hamlet", "suburb", "city_district", "county")
_REGION_KEYS = ("state", "region", "province", "state_district", "county")
_CACHE_TTL_S = 7 * 24 * 3600
_CACHE_MAX = 2048
_COOLDOWN_S = 30.0
_BLOCKED_COOLDOWN_S = 600.0


class ContextUnavailable(Exception):
    """The provider could not answer. The message is safe to show to users."""


@dataclass(frozen=True)
class PlaceContext:
    status: str  # "ok" | "cached" | "stale" | "no_result"
    country: str | None = None
    country_code: str | None = None
    admin_region: str | None = None
    place: str | None = None

    @property
    def label(self) -> str | None:
        parts: list[str] = []
        for part in (self.place, self.admin_region, self.country):
            if part and part not in parts:
                parts.append(part)
        return ", ".join(parts) or None


class ContextProvider(Protocol):
    id: str
    attribution: str

    def availability(self) -> tuple[bool, str | None]: ...

    def reverse(self, lat: float, lon: float, *, deadline: float | None = None) -> PlaceContext:
        """Raises ContextUnavailable. `deadline` is an absolute time.monotonic() value."""
        ...


class NominatimProvider:
    """OSM Nominatim reverse geocoding under its usage policy: identifying User-Agent, at most one
    request per second, results cached, no bulk use. Only model-predicted coordinates are sent, never the image."""

    id = "nominatim"
    attribution = ATTRIBUTION

    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
        backoff_s: float = 0.5,
    ):
        self.settings = settings
        self._client = client
        self._clock = clock
        self._sleep = sleep
        self.max_attempts = max(1, max_attempts)
        self.backoff_s = backoff_s
        self._lock = threading.Lock()
        self._last_request = -1e9
        self._blocked_until = 0.0
        self._failures = 0
        self._cache: OrderedDict[tuple[float, float], tuple[float, PlaceContext]] = OrderedDict()
        self.requests_made = 0

    def availability(self) -> tuple[bool, str | None]:
        if not self.settings.context_enabled:
            return False, "disabled (OPERA_CONTEXT_ENABLED=false)"
        return True, None

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(headers={"User-Agent": self.settings.context_user_agent})
        return self._client

    def _cached(self, key) -> tuple[PlaceContext, bool] | None:
        hit = self._cache.get(key)
        if hit is None:
            return None
        stored_at, value = hit
        return value, (self._clock() - stored_at) <= _CACHE_TTL_S

    def reverse(self, lat: float, lon: float, *, deadline: float | None = None) -> PlaceContext:
        ready, reason = self.availability()
        if not ready:
            raise ContextUnavailable(reason or "disabled")
        key = (round(lat, 3), round(lon, 3))
        with self._lock:
            hit = self._cached(key)
            if hit and hit[1]:
                self._cache.move_to_end(key)
                return _with_status(hit[0], "cached")
            try:
                value = self._fetch(key, deadline)
            except ContextUnavailable:
                if hit:  # stale beats nothing
                    return _with_status(hit[0], "stale")
                raise
            self._cache[key] = (self._clock(), value)
            self._cache.move_to_end(key)
            while len(self._cache) > _CACHE_MAX:
                self._cache.popitem(last=False)
            return value

    def _remaining(self, deadline: float | None) -> float | None:
        return None if deadline is None else deadline - self._clock()

    def _fetch(self, key: tuple[float, float], deadline: float | None) -> PlaceContext:
        if self._clock() < self._blocked_until:
            raise ContextUnavailable("provider cooling down after errors")
        last_error = "no attempt made"
        for attempt in range(self.max_attempts):
            wait = max(0.0, self._last_request + self.settings.context_min_interval_s - self._clock())
            if attempt:
                wait = max(wait, self.backoff_s * 2 ** (attempt - 1))
            remaining = self._remaining(deadline)
            if remaining is not None and wait >= remaining:
                raise ContextUnavailable("time budget exhausted")
            if wait:
                self._sleep(wait)
            timeout = self.settings.context_timeout_s
            remaining = self._remaining(deadline)
            if remaining is not None:
                timeout = min(timeout, max(0.2, remaining))
            self._last_request = self._clock()
            self.requests_made += 1
            try:
                response = self._http().get(
                    f"{self.settings.context_base_url.rstrip('/')}/reverse",
                    params={
                        "format": "jsonv2",
                        "lat": f"{key[0]:.3f}",
                        "lon": f"{key[1]:.3f}",
                        "zoom": 10,
                        "addressdetails": 1,
                        "accept-language": "en",
                    },
                    headers={"User-Agent": self.settings.context_user_agent},
                    timeout=timeout,
                )
            except httpx.HTTPError as exc:
                last_error = type(exc).__name__
                continue
            if response.status_code in (403, 429):  # policy block or rate limit: do not retry, back off
                self._blocked_until = self._clock() + _BLOCKED_COOLDOWN_S
                raise ContextUnavailable(f"provider refused the request (HTTP {response.status_code})")
            if response.status_code >= 500:
                last_error = f"HTTP {response.status_code}"
                continue
            if response.status_code != 200:
                self._record_failure()
                raise ContextUnavailable(f"unexpected response (HTTP {response.status_code})")
            try:
                payload = response.json()
            except ValueError:
                self._record_failure()
                raise ContextUnavailable("provider returned invalid JSON") from None
            self._failures = 0
            return _parse(payload)
        self._record_failure()
        raise ContextUnavailable(f"provider did not answer ({last_error})")

    def _record_failure(self) -> None:
        self._failures += 1
        if self._failures >= 3:
            self._blocked_until = self._clock() + _COOLDOWN_S
            self._failures = 0


def _with_status(value: PlaceContext, status: str) -> PlaceContext:
    return PlaceContext(status, value.country, value.country_code, value.admin_region, value.place)


def _clean(value) -> str | None:
    return value.strip()[:120] if isinstance(value, str) and value.strip() else None


def _parse(payload) -> PlaceContext:
    address = payload.get("address") if isinstance(payload, dict) and not payload.get("error") else None
    if not isinstance(address, dict):
        return PlaceContext("no_result")  # open ocean or unmapped: a valid answer, not a failure
    place = next((v for k in _PLACE_KEYS if (v := _clean(address.get(k)))), None)
    region = next((v for k in _REGION_KEYS if (v := _clean(address.get(k))) and v != place), None)
    code = _clean(address.get("country_code"))
    return PlaceContext(
        "ok",
        country=_clean(address.get("country")),
        country_code=code.upper()[:8] if code else None,
        admin_region=region,
        place=place,
    )
