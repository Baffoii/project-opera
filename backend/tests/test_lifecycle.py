from __future__ import annotations
import pytest


from datetime import timedelta

from sqlalchemy import func, select

from app.db import AnalysisRow, AuditLogRow, CandidateRow, UploadRow, session_scope, utcnow
from app.services.pipeline import band_for
from app.services.sweeper import sweep_expired

from .conftest import ANALYZE_FORM, HEADERS, analyze_files


def _analyze(client, data, **form):
    return client.post("/api/v1/analyze", headers=HEADERS, files=analyze_files(data), data={**ANALYZE_FORM, **form})


def _count(ctx, model):
    with session_scope(ctx.session_factory) as s:
        return s.scalar(select(func.count()).select_from(model))


def test_analyze_get_delete_lifecycle(client, ctx, jpeg_bytes):
    r = _analyze(client, jpeg_bytes())
    assert r.status_code == 200
    body = r.json()
    aid = body["id"]
    assert body["status"] == "complete" and body["model_kind"] == "mock"
    assert 1 <= len(body["candidates"]) <= 5
    assert [c["rank"] for c in body["candidates"]] == list(range(1, len(body["candidates"]) + 1))
    scores = [c["score"] for c in body["candidates"]]
    assert scores == sorted(scores, reverse=True)
    for c in body["candidates"]:
        assert c["uncalibrated"] is True
        assert c["source_model"].startswith("mock@")
        assert c["confidence_band"] in ("low", "medium", "high")
        assert c["label"].startswith("MOCK:")
    assert body["clues_kind"] == "none" and body["clues"] == []
    assert "total" in body["latency_ms"] and "sanitize" in body["latency_ms"]
    assert body["cost_estimate_usd"] is None

    got = client.get(f"/api/v1/analyses/{aid}", headers=HEADERS)
    assert got.status_code == 200 and got.json()["candidates"] == body["candidates"]
    assert len(list(ctx.settings.storage_dir.iterdir())) == 1

    assert client.delete(f"/api/v1/analyses/{aid}", headers=HEADERS).status_code == 204
    assert client.get(f"/api/v1/analyses/{aid}", headers=HEADERS).status_code == 404
    assert client.delete(f"/api/v1/analyses/{aid}", headers=HEADERS).status_code == 404
    assert list(ctx.settings.storage_dir.iterdir()) == []
    assert _count(ctx, UploadRow) == _count(ctx, AnalysisRow) == _count(ctx, CandidateRow) == 0


def test_mock_output_is_deterministic_per_image(client, jpeg_bytes):
    a = _analyze(client, jpeg_bytes()).json()["candidates"]
    b = _analyze(client, jpeg_bytes()).json()["candidates"]
    c = _analyze(client, jpeg_bytes(color=(0, 255, 0), size=(33, 91))).json()["candidates"]
    assert a == b and a != c


def test_vlm_clues_requested_but_unavailable_is_reported_not_faked(client, jpeg_bytes):
    body = _analyze(client, jpeg_bytes(), use_vlm_clues="true").json()
    assert body["clues"] == [] and body["clues_kind"] == "none"
    assert any("VLM clues unavailable" in n for n in body["notices"])


def test_metadata_free_false_is_ignored_with_notice(client, jpeg_bytes):
    body = _analyze(client, jpeg_bytes(), metadata_free="false").json()
    assert any("always strips" in n for n in body["notices"])


def test_cascade_delete_from_uploads(client, ctx, jpeg_bytes):
    _analyze(client, jpeg_bytes())
    assert _count(ctx, CandidateRow) > 0
    with session_scope(ctx.session_factory) as s:
        s.delete(s.scalars(select(UploadRow)).first())
    assert _count(ctx, AnalysisRow) == 0 and _count(ctx, CandidateRow) == 0


def test_ttl_sweeper_removes_expired_files_and_rows(client, ctx, jpeg_bytes):
    old = _analyze(client, jpeg_bytes()).json()["id"]
    fresh = _analyze(client, jpeg_bytes(color=(1, 2, 3), size=(20, 20))).json()["id"]
    assert len(list(ctx.settings.storage_dir.iterdir())) == 2
    with session_scope(ctx.session_factory) as s:
        row = s.get(AnalysisRow, old)
        row.upload.expires_at = utcnow() - timedelta(minutes=1)
        row.expires_at = utcnow() - timedelta(minutes=1)
    # expired analyses are already invisible before the sweeper runs
    assert client.get(f"/api/v1/analyses/{old}", headers=HEADERS).status_code == 404
    assert sweep_expired(ctx) == 1
    assert len(list(ctx.settings.storage_dir.iterdir())) == 1
    assert client.get(f"/api/v1/analyses/{fresh}", headers=HEADERS).status_code == 200
    assert _count(ctx, UploadRow) == _count(ctx, AnalysisRow) == 1
    assert sweep_expired(ctx) == 0


def test_expiry_follows_configured_ttl(client, jpeg_bytes, settings):
    body = _analyze(client, jpeg_bytes()).json()
    from datetime import datetime

    created = datetime.fromisoformat(body["created_at"])
    expires = datetime.fromisoformat(body["expires_at"])
    assert abs((expires - created) - timedelta(hours=settings.upload_ttl_hours)) < timedelta(seconds=1)


def test_audit_log_has_metadata_only(client, ctx, jpeg_bytes):
    r = _analyze(client, jpeg_bytes())
    aid = r.json()["id"]
    client.get(f"/api/v1/analyses/{aid}", headers=HEADERS)
    client.get("/api/v1/models")  # unauthenticated: still audited with 401
    with session_scope(ctx.session_factory) as s:
        rows = s.scalars(select(AuditLogRow)).all()
        dump = " ".join(
            f"{x.request_id} {x.endpoint} {x.client_hash} {x.model} {x.status}" for x in rows
        )
    assert len(rows) == 3
    assert rows[0].endpoint == "POST /api/v1/analyze" and rows[0].model == "mock" and rows[0].status == 200
    assert rows[1].endpoint == "GET /api/v1/analyses/{analysis_id}"  # route template, not the id
    assert rows[2].status == 401
    assert aid not in dump and "testclient" not in dump and "photo.jpg" not in dump
    assert all(len(x.client_hash) == 32 for x in rows)
    assert r.headers["X-Request-ID"] == rows[0].request_id


def test_band_thresholds_and_abstention(tmp_path, jpeg_bytes):
    assert band_for(0.6, 0.5, 0.15) == "high"
    assert band_for(0.5, 0.5, 0.15) == "high"
    assert band_for(0.2, 0.5, 0.15) == "medium"
    assert band_for(0.01, 0.5, 0.15) == "low"

    from fastapi.testclient import TestClient

    from app.adapters.base import GeoResult, RawCandidate
    from app.main import create_app

    from .conftest import make_ctx, make_settings

    class Weak:
        id, version, kind = "mock", "weak-0", "mock"

        def availability(self):
            return True, None

        def predict(self, image_bytes, *, image_sha256, top_k=5):
            return GeoResult([RawCandidate(1.0, 2.0, 0.005), RawCandidate(3.0, 4.0, 0.001)])

    s = make_settings(tmp_path)
    c = make_ctx(s)
    c.geo_adapters["mock"] = Weak()
    with TestClient(create_app(s, c)) as tc:
        body = _analyze(tc, jpeg_bytes()).json()
    assert body["status"] == "abstained" and body["candidates"] == []
    assert body["abstain_reason"]


def test_adapter_failure_is_recorded_as_failed(tmp_path, jpeg_bytes):
    from fastapi.testclient import TestClient

    from app.main import create_app

    from .conftest import make_ctx, make_settings

    class Boom:
        id, version, kind = "mock", "boom-0", "mock"

        def availability(self):
            return True, None

        def predict(self, *a, **k):
            raise RuntimeError("secret internal detail")

    s = make_settings(tmp_path)
    c = make_ctx(s)
    c.geo_adapters["mock"] = Boom()
    with TestClient(create_app(s, c)) as tc:
        r = _analyze(tc, jpeg_bytes())
    assert r.status_code == 200 and r.json()["status"] == "failed"
    assert "secret internal detail" not in r.text


def test_clue_adapter_output_is_stored_separately_with_cost(tmp_path, jpeg_bytes):
    from fastapi.testclient import TestClient

    from app.adapters.base import ClueResult
    from app.main import create_app

    from .conftest import make_ctx, make_settings

    class FakeClues:
        id, version, kind = "vlm-clues", "fake-0", "real"

        def availability(self):
            return True, None

        def extract(self, image_bytes, *, mime):
            return ClueResult(
                clues=[{"category": "road", "text": "Dashed yellow centre line", "certainty": "observed"}],
                region_guesses=["North America"],
                input_tokens=1000,
                output_tokens=200,
                prompt_version="p-test",
                model_name="fake-model",
            )

    s = make_settings(tmp_path, vlm_price_input_per_mtok=2.0, vlm_price_output_per_mtok=10.0)
    c = make_ctx(s)
    c.clue_adapters["vlm-clues"] = FakeClues()
    with TestClient(create_app(s, c)) as tc:
        body = _analyze(tc, jpeg_bytes(), use_vlm_clues="true").json()
        again = tc.get(f"/api/v1/analyses/{body['id']}", headers=HEADERS).json()
    assert body["clues_kind"] == "real" and body["clues"][0]["text"].startswith("Dashed")
    assert body["clue_model_region_guesses"] == [{"region": "North America"}]
    assert all("North America" not in str(cand) for cand in body["candidates"])  # guesses never become candidates
    assert body["cost_estimate_usd"] == pytest.approx(0.004)
    assert body["versions"]["prompt"] == "p-test" and body["model_kind"] == "mock"
    assert again == body
