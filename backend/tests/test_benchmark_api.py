from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.eval.synthetic import SYNTHETIC_ID, write_synthetic_dataset
from app.main import create_app

from .conftest import HEADERS, make_ctx, make_settings


@pytest.fixture
def client(tmp_path):
    write_synthetic_dataset(tmp_path / "bench")
    settings = make_settings(tmp_path, benchmark_dir=tmp_path / "bench")
    with TestClient(create_app(settings, make_ctx(settings))) as c:
        yield c


def get(client, path, **params):
    return client.get(path, params=params, headers=HEADERS)


def test_datasets_listing(client):
    body = get(client, "/api/v1/benchmark/datasets").json()
    assert body[0]["id"] == SYNTHETIC_ID and body[0]["splits"]["seed"] == {"items": 4, "images_present": 4}
    assert body[0]["image_source_types"] == ["synthetic"]


def test_rounds_carry_no_truth_and_are_seeded(client):
    a = get(client, "/api/v1/benchmark/rounds", dataset=SYNTHETIC_ID, split="all", n=3, seed=5).json()
    b = get(client, "/api/v1/benchmark/rounds", dataset=SYNTHETIC_ID, split="all", n=3, seed=5).json()
    assert a == b and len(a["rounds"]) == 3
    text = str(a)
    for forbidden in ("lat", "lon", "country", "license", "author", "FR", "filename"):
        assert forbidden not in text.replace("image_id", "").replace("dataset", "")
    assert get(client, "/api/v1/benchmark/rounds", dataset="nope").status_code == 404
    assert get(client, "/api/v1/benchmark/rounds", dataset=SYNTHETIC_ID, split="train").status_code == 400
    assert get(client, "/api/v1/benchmark/rounds", dataset=SYNTHETIC_ID, n=0).status_code == 422


def test_rounds_skip_images_that_are_not_present(client, tmp_path):
    for p in (tmp_path / "bench" / SYNTHETIC_ID / "images").glob("syn0[0-6].png"):
        p.unlink()
    body = get(client, "/api/v1/benchmark/rounds", dataset=SYNTHETIC_ID, split="all", n=50).json()
    assert [r["image_id"] for r in body["rounds"]] == ["syn07"]
    (tmp_path / "bench" / SYNTHETIC_ID / "images" / "syn07.png").unlink()
    assert get(client, "/api/v1/benchmark/rounds", dataset=SYNTHETIC_ID, split="all").status_code == 404


def test_image_endpoint_serves_sanitized_pixels(client):
    response = get(client, f"/api/v1/benchmark/images/{SYNTHETIC_ID}/syn00")
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(response.content)).size == (128, 96)
    assert get(client, f"/api/v1/benchmark/images/{SYNTHETIC_ID}/ghost").status_code == 404
    assert get(client, "/api/v1/benchmark/images/nope/syn00").status_code == 404


def test_play_reveals_truth_attribution_user_and_model(client):
    response = client.post(
        "/api/v1/benchmark/play",
        json={"dataset": SYNTHETIC_ID, "image_id": "syn00", "model": "mock", "guess": {"lat": 48.86, "lon": 2.35}},
        headers=HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["truth"]["lat"] == 48.86 and body["truth"]["country"] == "FR"
    assert body["attribution"]["license"].startswith("CC0") and body["attribution"]["license_status"] == "needs_human_review"
    assert body["user"]["error_km"] == 0 and body["user"]["score"] == 5000
    model = body["model"]
    assert model["kind"] == "mock" and model["status"] == "complete" and len(model["candidates"]) == 5
    assert all(c["uncalibrated"] for c in model["candidates"])
    assert model["top1_error_km"] == model["candidates"][0]["error_km"]
    assert "not a model metric" in body["score_note"]


def test_play_without_a_guess_and_with_unavailable_model(client):
    body = client.post(
        "/api/v1/benchmark/play",
        json={"dataset": SYNTHETIC_ID, "image_id": "syn01", "model": "geoclip-v1", "guess": None},
        headers=HEADERS,
    ).json()
    assert body["user"] is None
    assert body["model"]["status"] == "unavailable" and body["model"]["candidates"] == []


def test_play_validation_and_auth(client):
    def play(**kw):
        return client.post("/api/v1/benchmark/play", json={"dataset": SYNTHETIC_ID, "image_id": "syn00", **kw}, headers=HEADERS)

    assert play(guess={"lat": 91, "lon": 0}).status_code == 422
    assert play(guess={"lat": 0, "lon": 181}).status_code == 422
    assert play(model="ghost").status_code == 400
    assert play(image_id="ghost").status_code == 404
    assert client.post("/api/v1/benchmark/play", json={"dataset": SYNTHETIC_ID, "image_id": "syn00"}).status_code == 401
    assert client.get("/api/v1/benchmark/datasets").status_code == 401
