from __future__ import annotations

from fastapi.testclient import TestClient

from app.adapters.base import GeoResult, RawCandidate
from app.geo.context_provider import ATTRIBUTION, ContextUnavailable, PlaceContext
from app.main import create_app

from .conftest import ANALYZE_FORM, HEADERS, analyze_files, make_ctx, make_settings


class ThreeGeo:
    id = "staged"
    version = "s1"
    kind = "real"

    def availability(self):
        return True, None

    def predict(self, image_bytes, *, image_sha256, top_k=5):
        return GeoResult(
            candidates=[
                RawCandidate(lat=38.7, lon=-9.1, score=0.2),
                RawCandidate(lat=40.4, lon=-3.7, score=0.1),
                RawCandidate(lat=0.0, lon=-30.0, score=0.02),
            ]
        )


class FakeProvider:
    id = "fake-osm"
    attribution = ATTRIBUTION

    def __init__(self, behaviour="ok"):
        self.behaviour, self.calls = behaviour, []

    def availability(self):
        return True, None

    def reverse(self, lat, lon, *, deadline=None):
        self.calls.append((lat, lon, deadline))
        if self.behaviour == "fail":
            raise ContextUnavailable("provider did not answer (ReadTimeout)")
        if self.behaviour == "bug":
            raise RuntimeError("secret internal detail")
        if self.behaviour == "fail-second" and len(self.calls) == 2:
            raise ContextUnavailable("provider did not answer (ReadTimeout)")
        if lat == 0.0:
            return PlaceContext("no_result")
        if lat > 40:
            return PlaceContext("cached", "Spain", "ES", "Community of Madrid", "Madrid")
        return PlaceContext("ok", "Portugal", "PT", None, "Lisbon")


def _client(tmp_path, provider, geo=None):
    settings = make_settings(tmp_path)
    ctx = make_ctx(settings, context_provider=provider)
    ctx.geo_adapters["staged"] = geo or ThreeGeo()
    return TestClient(create_app(settings, ctx))


def _post(client, data, model="staged"):
    r = client.post(
        "/api/v1/analyze", headers=HEADERS, files=analyze_files(data), data={**ANALYZE_FORM, "model": model}
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_candidates_get_place_names_context_and_osm_attribution(tmp_path, jpeg_bytes):
    provider = FakeProvider()
    with _client(tmp_path, provider) as client:
        body = _post(client, jpeg_bytes())
        again = client.get(f"/api/v1/analyses/{body['id']}", headers=HEADERS).json()
    first, second, ocean = body["candidates"]
    assert first["label"] == "Lisbon, Portugal" and first["country_code"] == "PT"
    assert first["context"] == {"status": "ok", "country": "Portugal", "admin_region": None, "place": "Lisbon"}
    assert second["label"] == "Madrid, Community of Madrid, Spain" and second["context"]["status"] == "cached"
    assert ocean["label"] is None and ocean["context"]["status"] == "no_result"
    assert ATTRIBUTION in [p.get("attribution") for p in body["provenance"]]
    assert "context" in body["latency_ms"]
    assert again == body  # persisted
    assert len(provider.calls) == 3 and all(d is not None for _, _, d in provider.calls)


def test_total_provider_failure_still_returns_candidates_with_notice(tmp_path, jpeg_bytes):
    provider = FakeProvider("fail")
    with _client(tmp_path, provider) as client:
        body = _post(client, jpeg_bytes())
    assert body["status"] == "complete" and len(body["candidates"]) == 3
    assert all(c["context"] == {"status": "unavailable", "country": None, "admin_region": None, "place": None} for c in body["candidates"])
    assert all(c["label"] is None for c in body["candidates"])
    assert any("Place names unavailable for 3 of 3" in n and "ReadTimeout" in n for n in body["notices"])
    assert ATTRIBUTION not in [p.get("attribution") for p in body["provenance"]]  # nothing from OSM was used
    assert len(provider.calls) == 1  # first failure short-circuits the rest


def test_partial_failure_keeps_earlier_names_and_credits_osm(tmp_path, jpeg_bytes):
    provider = FakeProvider("fail-second")
    with _client(tmp_path, provider) as client:
        body = _post(client, jpeg_bytes())
    statuses = [c["context"]["status"] for c in body["candidates"]]
    assert statuses == ["ok", "unavailable", "unavailable"]
    assert body["candidates"][0]["label"] == "Lisbon, Portugal"
    assert any("2 of 3" in n for n in body["notices"])
    assert ATTRIBUTION in [p.get("attribution") for p in body["provenance"]]


def test_provider_bug_does_not_fail_analysis_or_leak_detail(tmp_path, jpeg_bytes):
    with _client(tmp_path, FakeProvider("bug")) as client:
        body = _post(client, jpeg_bytes())
    joined = " ".join(body["notices"])
    assert body["status"] == "complete" and "RuntimeError" in joined and "secret internal detail" not in joined


def test_mock_candidates_are_never_sent_to_the_provider(tmp_path, jpeg_bytes):
    provider = FakeProvider()
    with _client(tmp_path, provider) as client:
        body = _post(client, jpeg_bytes(), model="mock")
    assert provider.calls == []
    assert body["model_kind"] == "mock" and all(c["context"] is None for c in body["candidates"])


def test_no_provider_configured_leaves_context_empty(tmp_path, jpeg_bytes):
    with _client(tmp_path, None) as client:
        body = _post(client, jpeg_bytes())
    assert body["status"] == "complete" and all(c["context"] is None for c in body["candidates"])


def test_abstained_analysis_does_not_geocode(tmp_path, jpeg_bytes):
    class Low(ThreeGeo):
        def predict(self, image_bytes, *, image_sha256, top_k=5):
            return GeoResult(candidates=[RawCandidate(lat=38.7, lon=-9.1, score=0.0001)])

    provider = FakeProvider()
    with _client(tmp_path, provider, geo=Low()) as client:
        body = _post(client, jpeg_bytes())
    assert body["status"] == "abstained" and provider.calls == []


def test_health_reports_the_context_provider(tmp_path):
    with _client(tmp_path, FakeProvider()) as client:
        body = client.get("/api/health").json()
    assert body["adapters"]["fake-osm"] == "ready"


def test_existing_database_gains_the_context_column(tmp_path):
    from sqlalchemy import create_engine, inspect, text

    from app.db import init_db

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE candidates (id INTEGER PRIMARY KEY, rank INTEGER)"))
    init_db(engine)
    assert "context" in {c["name"] for c in inspect(engine).get_columns("candidates")}
    init_db(engine)  # idempotent
