from __future__ import annotations

from app.adapters.base import ClueError, ClueResult, GeoResult, RawCandidate

from .conftest import ANALYZE_FORM, HEADERS, analyze_files, make_ctx, make_settings
from fastapi.testclient import TestClient
from app.main import create_app


class FakeClues:
    id = "vlm-clues"
    version = "fake"
    kind = "real"

    def __init__(self, result=None, error=None):
        self._result, self._error = result, error

    def availability(self):
        return True, None

    def extract(self, image_bytes, *, mime):
        if self._error:
            raise self._error
        return self._result


class StagedGeo:
    id = "staged"
    version = "s1"
    kind = "real"

    def availability(self):
        return True, None

    def predict(self, image_bytes, *, image_sha256, top_k=5):
        return GeoResult(
            candidates=[RawCandidate(lat=10.0, lon=10.0, score=0.2)],
            stages={"model_infer": 12.5, "model_load": 3000.0},
            notes={"nms_km": 50.0},
        )


def _client(tmp_path, clue=None, **overrides):
    settings = make_settings(tmp_path, **overrides)
    ctx = make_ctx(settings)
    ctx.geo_adapters["staged"] = StagedGeo()
    if clue is not None:
        ctx.clue_adapters["vlm-clues"] = clue
    return TestClient(create_app(settings, ctx))


def _post(client, data, **form):
    r = client.post(
        "/api/v1/analyze",
        headers=HEADERS,
        files=analyze_files(data),
        data={**ANALYZE_FORM, "use_vlm_clues": "true", **form},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_without_vlm_falls_back_to_labelled_mock_clues(tmp_path, jpeg_bytes):
    with _client(tmp_path) as client:
        body = _post(client, jpeg_bytes())
    assert body["clues_kind"] == "mock"
    assert body["clues"] and all(c["text"].startswith("MOCK:") for c in body["clues"])
    assert any("MOCK clues" in n and "no key" in n for n in body["notices"])
    assert body["status"] == "complete"  # mock clues never change the geolocation status


def test_real_clues_are_stored_with_cost_and_versions(tmp_path, jpeg_bytes):
    result = ClueResult(
        clues=[{"category": "road", "text": "Drives on the left", "certainty": "observed"}],
        region_guesses=["Japan"],
        input_tokens=2000,
        output_tokens=100,
        prompt_version="p1",
        model_name="m1",
    )
    with _client(tmp_path, FakeClues(result), vlm_price_input_per_mtok=1.0, vlm_price_output_per_mtok=2.0) as client:
        body = _post(client, jpeg_bytes())
        again = client.get(f"/api/v1/analyses/{body['id']}", headers=HEADERS).json()
    assert body["clues_kind"] == "real" and body["clues"][0]["text"] == "Drives on the left"
    assert body["cost_estimate_usd"] == 0.0022
    assert body["versions"]["prompt"] == "p1" and body["versions"]["clue_model"] == "m1"
    assert body["versions"]["clue_tokens"] == {"input": 2000, "output": 100}
    assert again == body


def test_model_abstain_makes_analysis_abstained_but_keeps_candidates_out_of_ranking_claims(tmp_path, jpeg_bytes):
    result = ClueResult(clues=[], region_guesses=[], abstain=True, abstain_reason="Indoor document")
    with _client(tmp_path, FakeClues(result)) as client:
        body = _post(client, jpeg_bytes(), model="staged")
    assert body["status"] == "abstained" and "Indoor document" in body["abstain_reason"]
    assert any("abstained" in n for n in body["notices"])


def test_refusal_notice_does_not_abstain(tmp_path, jpeg_bytes):
    result = ClueResult(clues=[], region_guesses=[], notices=["The clue model declined to describe this image; no clues are shown."])
    with _client(tmp_path, FakeClues(result)) as client:
        body = _post(client, jpeg_bytes(), model="staged")
    assert body["status"] == "complete" and body["clues"] == []
    assert any("declined" in n for n in body["notices"])


def test_clue_failure_is_a_notice_and_geolocation_continues(tmp_path, jpeg_bytes):
    with _client(tmp_path, FakeClues(error=ClueError("TimeoutError"))) as client:
        body = _post(client, jpeg_bytes(), model="staged")
        raw = client.get(f"/api/v1/analyses/{body['id']}", headers=HEADERS).text
    assert body["status"] == "complete" and len(body["candidates"]) == 1
    assert any("TimeoutError" in n for n in body["notices"])
    assert "sk-" not in raw


def test_unexpected_clue_exception_only_exposes_type_name(tmp_path, jpeg_bytes):
    with _client(tmp_path, FakeClues(error=RuntimeError("secret detail sk-abc"))) as client:
        body = _post(client, jpeg_bytes(), model="staged")
    joined = " ".join(body["notices"])
    assert "RuntimeError" in joined and "secret detail" not in joined


def test_geo_stages_and_notes_are_merged_into_latency_and_versions(tmp_path, jpeg_bytes):
    with _client(tmp_path) as client:
        body = _post(client, jpeg_bytes(), model="staged", use_vlm_clues="false")
    assert body["latency_ms"]["model_infer"] == 12.5 and body["latency_ms"]["model_load"] == 3000.0
    assert body["versions"]["nms_km"] == 50.0
    assert body["clues_kind"] == "none"


def test_health_lists_both_clue_adapters_and_mock_clues_ready(tmp_path):
    with _client(tmp_path) as client:
        body = client.get("/api/health").json()
    assert body["adapters"]["mock-clues"] == "ready"
