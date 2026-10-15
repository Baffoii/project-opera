from __future__ import annotations

import io

import pytest

from app.adapters.geoclip import GeoClipAdapter, suppress_nearby
from app.geo.haversine import haversine_km

from .conftest import make_settings


def test_nms_drops_near_duplicates_but_keeps_raw_scores():
    pts = [
        (48.8566, 2.3522, 0.30),  # Paris
        (48.90, 2.40, 0.25),  # ~6 km from Paris: suppressed
        (51.5074, -0.1278, 0.20),  # London
        (48.70, 2.20, 0.10),  # suppressed by Paris
        (40.7128, -74.0060, 0.05),  # New York
    ]
    kept = suppress_nearby(pts, top_k=5, min_km=50)
    assert kept == [pts[0], pts[2], pts[4]]


def test_nms_respects_top_k_and_ordering():
    pts = [(float(i), 0.0, 1.0 - i / 100) for i in range(0, 40, 5)]
    kept = suppress_nearby(pts, top_k=3, min_km=50)
    assert [p[2] for p in kept] == sorted((p[2] for p in kept), reverse=True)
    assert len(kept) == 3


class _FakeTensorLike:
    def __init__(self, data):
        self._data = data

    def tolist(self):
        return self._data


class _FakeModel:
    def __init__(self):
        self.seen_top_k = None
        self.input_was_bytesio = False

    def predict(self, image, top_k):
        self.seen_top_k = top_k
        self.input_was_bytesio = isinstance(image, io.BytesIO)
        gps = [[48.85, 2.35], [48.86, 2.36], [51.5, -0.12], [35.68, 139.69], [-33.87, 151.2], [40.7, -74.0]]
        scores = [0.4, 0.3, 0.1, 0.05, 0.03, 0.02]
        return _FakeTensorLike(gps), _FakeTensorLike(scores)


def test_predict_uses_pool_nms_and_reports_stages(tmp_path):
    adapter = GeoClipAdapter(make_settings(tmp_path, geoclip_pool=50, geoclip_nms_km=50.0))
    adapter._model = _FakeModel()
    result = adapter.predict(b"jpegbytes", image_sha256="x", top_k=5)
    assert adapter._model.seen_top_k == 50 and adapter._model.input_was_bytesio
    assert len(result.candidates) == 5
    scores = [c.score for c in result.candidates]
    assert scores == sorted(scores, reverse=True)
    assert 0.3 not in scores  # the second Paris point was suppressed; its score is not merged into the first
    assert "model_infer" in result.stages and "model_load" not in result.stages
    assert result.notes["score"] == "raw gallery softmax mass" and result.notes["nms_km"] == 50.0


def test_availability_reports_missing_package(tmp_path, monkeypatch):
    import importlib.util

    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: None if name == "geoclip" else real(name, *a))
    ok, reason = GeoClipAdapter(make_settings(tmp_path)).availability()
    assert not ok and "geoclip" in reason


@pytest.mark.slow
def test_real_geoclip_inference_on_synthetic_image(tmp_path, jpeg_bytes):
    """Runs the real pretrained model on CPU. Skipped unless torch/geoclip import and weights load."""
    adapter = GeoClipAdapter(make_settings(tmp_path))
    ok, reason = adapter.availability()
    if not ok:
        pytest.skip(reason)
    try:
        result = adapter.predict(jpeg_bytes(size=(320, 240), color=(90, 140, 200)), image_sha256="x", top_k=5)
    except Exception as exc:  # e.g. CLIP backbone not downloadable offline
        pytest.skip(f"model could not load: {type(exc).__name__}")
    cands = result.candidates
    assert len(cands) == 5
    assert all(-90 <= c.lat <= 90 and -180 <= c.lon <= 180 for c in cands)
    assert [c.score for c in cands] == sorted((c.score for c in cands), reverse=True)
    for i, a in enumerate(cands):
        for b in cands[i + 1 :]:
            assert haversine_km(a.lat, a.lon, b.lat, b.lon) >= 50.0
