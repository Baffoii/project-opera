from __future__ import annotations

import httpx
import pytest

from app.geo.context_provider import ContextUnavailable, NominatimProvider, PlaceContext

from .conftest import make_settings

LISBON = {
    "address": {
        "city": "Lisbon",
        "state": "Lisbon",
        "country": "Portugal",
        "country_code": "pt",
    }
}


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def _provider(tmp_path, responses, **kw):
    """responses: list of httpx.Response / Exception consumed in order (last one repeats)."""
    clock = Clock()
    seen: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item

    provider = NominatimProvider(
        make_settings(tmp_path, context_user_agent="OPERA-test/1.0 (https://example.invalid/contact)"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=clock,
        sleep=clock.sleep,
        **kw,
    )
    return provider, clock, seen


def _ok(payload=LISBON):
    return httpx.Response(200, json=payload)


def test_parses_place_region_country_and_sends_policy_headers(tmp_path):
    provider, _, seen = _provider(tmp_path, [_ok()])
    result = provider.reverse(38.7223, -9.1393)
    assert result.status == "ok" and result.admin_region is None
    assert result.place == "Lisbon" and result.country == "Portugal" and result.country_code == "PT"
    assert result.label == "Lisbon, Portugal"  # region equal to place is not repeated
    request = seen[0]
    assert request.headers["user-agent"].startswith("OPERA-test/1.0")
    assert request.url.params["lat"] == "38.722" and request.url.params["lon"] == "-9.139"  # coordinates are rounded
    assert request.url.params["format"] == "jsonv2" and request.url.params["zoom"] == "10"


def test_repeat_lookup_is_served_from_cache_without_a_second_request(tmp_path):
    provider, _, seen = _provider(tmp_path, [_ok()])
    first = provider.reverse(38.7223, -9.1393)
    second = provider.reverse(38.7221, -9.1394)  # same 3-decimal cell
    assert first.status == "ok" and second.status == "cached" and second.label == first.label
    assert len(seen) == 1


def test_stale_cache_is_served_when_provider_fails(tmp_path):
    provider, clock, seen = _provider(tmp_path, [_ok(), httpx.Response(500)])
    provider.reverse(10.0, 10.0)
    clock.now += 8 * 24 * 3600  # past the 7-day TTL
    result = provider.reverse(10.0, 10.0)
    assert result.status == "stale" and result.country == "Portugal"
    assert len(seen) == 1 + provider.max_attempts


def test_ocean_is_no_result_not_a_failure(tmp_path):
    provider, _, _ = _provider(tmp_path, [_ok({"error": "Unable to geocode"})])
    result = provider.reverse(0.0, -30.0)
    assert result.status == "no_result" and result.label is None


def test_server_errors_retry_with_backoff_then_succeed(tmp_path):
    provider, clock, seen = _provider(tmp_path, [httpx.Response(503), httpx.Response(502), _ok()])
    assert provider.reverse(1.0, 1.0).status == "ok"
    assert len(seen) == 3 and all(s > 0 for s in clock.sleeps)
    assert max(clock.sleeps) >= 1.0  # exponential backoff on top of the rate limit


def test_timeouts_exhaust_retries_and_raise(tmp_path):
    provider, _, seen = _provider(tmp_path, [httpx.ReadTimeout("slow")])
    with pytest.raises(ContextUnavailable) as info:
        provider.reverse(1.0, 1.0)
    assert "ReadTimeout" in str(info.value) and len(seen) == provider.max_attempts


def test_rate_limit_response_is_not_retried_and_starts_a_cooldown(tmp_path):
    provider, clock, seen = _provider(tmp_path, [httpx.Response(429), _ok()])
    with pytest.raises(ContextUnavailable):
        provider.reverse(1.0, 1.0)
    assert len(seen) == 1
    with pytest.raises(ContextUnavailable) as info:
        provider.reverse(2.0, 2.0)
    assert "cooling down" in str(info.value) and len(seen) == 1
    clock.now += 601
    assert provider.reverse(2.0, 2.0).status == "ok"


def test_requests_are_spaced_at_least_the_minimum_interval(tmp_path):
    provider, clock, seen = _provider(tmp_path, [_ok()])
    stamps: list[float] = []
    original = provider._http().get

    def spy(*a, **kw):
        stamps.append(clock.now)
        return original(*a, **kw)

    provider._client.get = spy
    for lat in (1.0, 2.0, 3.0):
        provider.reverse(lat, lat)
    assert len(stamps) == 3
    assert all(b - a >= provider.settings.context_min_interval_s - 1e-9 for a, b in zip(stamps, stamps[1:]))


def test_deadline_is_respected_without_sleeping_past_it(tmp_path):
    provider, clock, seen = _provider(tmp_path, [_ok()])
    provider.reverse(1.0, 1.0)
    with pytest.raises(ContextUnavailable) as info:
        provider.reverse(2.0, 2.0, deadline=clock.now + 0.2)  # the 1.1 s throttle cannot fit
    assert "budget" in str(info.value) and len(seen) == 1


def test_invalid_json_and_unexpected_status_are_failures_without_detail(tmp_path):
    provider, _, _ = _provider(tmp_path, [httpx.Response(200, content=b"<html>secret-ish</html>")])
    with pytest.raises(ContextUnavailable) as info:
        provider.reverse(1.0, 1.0)
    assert "secret-ish" not in str(info.value)
    provider, _, _ = _provider(tmp_path, [httpx.Response(404)])
    with pytest.raises(ContextUnavailable):
        provider.reverse(1.0, 1.0)


def test_repeated_failures_trigger_a_short_cooldown(tmp_path):
    provider, clock, seen = _provider(tmp_path, [httpx.Response(404)])
    for lat in (1.0, 2.0, 3.0):
        with pytest.raises(ContextUnavailable):
            provider.reverse(lat, lat)
    count = len(seen)
    with pytest.raises(ContextUnavailable) as info:
        provider.reverse(4.0, 4.0)
    assert "cooling down" in str(info.value) and len(seen) == count


def test_disabled_provider_is_unavailable(tmp_path):
    provider = NominatimProvider(make_settings(tmp_path, context_enabled=False))
    assert provider.availability()[0] is False
    with pytest.raises(ContextUnavailable):
        provider.reverse(1.0, 1.0)
    provider.close()


def test_label_deduplicates_and_handles_empty():
    assert PlaceContext("ok", country="Monaco", admin_region="Monaco", place="Monaco").label == "Monaco"
    assert PlaceContext("no_result").label is None
