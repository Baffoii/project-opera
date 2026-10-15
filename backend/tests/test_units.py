from __future__ import annotations

import pytest

from app.geo.haversine import haversine_km
from app.services.ratelimit import TokenBucketLimiter
from app.services.storage import LocalStorage


def test_haversine_known_distances():
    assert haversine_km(0, 0, 0, 0) == 0
    assert haversine_km(51.5074, -0.1278, 48.8566, 2.3522) == pytest.approx(343.5, abs=2)  # London-Paris
    assert haversine_km(0, 0, 0, 180) == pytest.approx(20015, abs=5)  # half circumference
    assert haversine_km(10, 20, 30, 40) == pytest.approx(haversine_km(30, 40, 10, 20))
    assert haversine_km(0, 179.9, 0, -179.9) == pytest.approx(22.2, abs=0.5)  # antimeridian


def test_token_bucket_refills_over_time():
    now = [0.0]
    limiter = TokenBucketLimiter(per_minute=60, burst=2, clock=lambda: now[0])
    assert limiter.acquire("a")[0] and limiter.acquire("a")[0]
    allowed, retry = limiter.acquire("a")
    assert not allowed and retry == pytest.approx(1.0)
    assert limiter.acquire("b")[0]  # separate client
    now[0] = 1.0
    assert limiter.acquire("a")[0]
    assert not limiter.acquire("a")[0]
    now[0] = 1000.0
    assert [limiter.acquire("a")[0] for _ in range(3)] == [True, True, False]  # capped at burst


def test_storage_keys_are_random_and_traversal_safe(tmp_path):
    store = LocalStorage(tmp_path / "s")
    k1, k2 = store.put(b"x"), store.put(b"x")
    assert k1 != k2 and store.read(k1) == b"x" and store.exists(k1)
    assert (tmp_path / "s" / k1).stat().st_mode & 0o777 == 0o600
    for bad in ("../etc/passwd", "a/b.img", "..", "x.img", k1 + "/..", "/abs"):
        with pytest.raises(ValueError):
            store.read(bad)
        with pytest.raises(ValueError):
            store.delete(bad)
    assert store.delete(k1) is True and store.delete(k1) is False and not store.exists(k1)
