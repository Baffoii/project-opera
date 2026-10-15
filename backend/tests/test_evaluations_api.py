from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.db import EvaluationItemRow, EvaluationRow, session_scope
from app.eval.synthetic import SYNTHETIC_ID, write_synthetic_dataset
from app.main import create_app
from app.services.evaluations import fail_interrupted

from .conftest import HEADERS, make_ctx, make_settings


@pytest.fixture
def eval_client(tmp_path):
    write_synthetic_dataset(tmp_path / "bench")
    settings = make_settings(tmp_path, benchmark_dir=tmp_path / "bench")
    ctx = make_ctx(settings)
    with TestClient(create_app(settings, ctx)) as c:
        c.ctx = ctx
        yield c


def _wait(client, evaluation_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/v1/evaluations/{evaluation_id}", headers=HEADERS).json()
        if body["status"] in ("complete", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError("evaluation did not finish")


def _start(client, **overrides):
    payload = {"dataset": SYNTHETIC_ID, "split": "all", "model": "mock", **overrides}
    return client.post("/api/v1/evaluations", json=payload, headers=HEADERS)


def test_evaluation_lifecycle_and_mock_labelling(eval_client):
    response = _start(eval_client)
    assert response.status_code == 202
    body = _wait(eval_client, response.json()["evaluation_id"])
    assert body["status"] == "complete" and body["error"] is None
    assert body["items_done"] == body["items_total"] == 8
    assert body["config"]["model_kind"] == "mock" and body["config"]["dataset"] == SYNTHETIC_ID
    assert body["config"]["dataset_version"] and body["config_hash"]
    overall = body["metrics"]["overall"]
    assert overall["n_items"] == 8 and overall["n_failed"] == 0 and overall["all"]["n"] == 8
    assert set(body["metrics"]["by_image_source_type"]) == {"synthetic"}
    assert body["metrics"]["reproducible_hash"] and body["started_at"] and body["finished_at"]
    with session_scope(eval_client.ctx.session_factory) as session:
        assert session.query(EvaluationItemRow).count() == 8


def test_same_config_gives_the_same_reproducible_hash(eval_client):
    a = _wait(eval_client, _start(eval_client, seed=1, limit=5).json()["evaluation_id"])
    b = _wait(eval_client, _start(eval_client, seed=1, limit=5).json()["evaluation_id"])
    c = _wait(eval_client, _start(eval_client, seed=2, limit=5).json()["evaluation_id"])
    assert a["config_hash"] == b["config_hash"] != c["config_hash"]
    assert a["metrics"]["reproducible_hash"] == b["metrics"]["reproducible_hash"]
    assert a["items_total"] == 5


def test_leakage_fails_the_run_with_a_clear_error(eval_client, tmp_path):
    root = tmp_path / "bench" / SYNTHETIC_ID
    manifest = (root / "manifest.csv").read_text(encoding="utf-8").splitlines()
    cols = manifest[0].split(",")
    fields = manifest[1].split(",")
    fields[cols.index("image_id")] = "dupe"
    fields[cols.index("split")] = "heldout"
    (root / "manifest.csv").write_text("\n".join([*manifest, ",".join(fields)]) + "\n", encoding="utf-8")
    body = _wait(eval_client, _start(eval_client).json()["evaluation_id"])
    assert body["status"] == "failed" and "Leakage between splits" in body["error"] and body["metrics"] is None


def test_request_errors(eval_client):
    assert _start(eval_client, dataset="nope").status_code == 404
    assert _start(eval_client, dataset="../x").status_code in (400, 404)
    assert _start(eval_client, model="ghost").status_code == 400
    assert _start(eval_client, model="geoclip-v1").status_code == 503  # registered but not installed in tests
    assert _start(eval_client, split="train").status_code == 400
    assert _start(eval_client, limit=0).status_code == 422
    assert eval_client.get("/api/v1/evaluations/nope", headers=HEADERS).status_code == 404
    assert eval_client.get("/api/v1/evaluations").status_code == 401
    assert eval_client.post("/api/v1/evaluations", json={"dataset": SYNTHETIC_ID}).status_code == 401


def test_unavailable_vlm_is_noted_and_never_replaced_by_mock_clues(eval_client):
    body = _wait(eval_client, _start(eval_client, use_vlm_clues=True, limit=2).json()["evaluation_id"])
    assert body["config"]["use_vlm_clues"] is False
    assert any("without clues" in n for n in body["metrics"]["notices"])


def test_list_and_interrupted_jobs(eval_client):
    _wait(eval_client, _start(eval_client, limit=2).json()["evaluation_id"])
    with session_scope(eval_client.ctx.session_factory) as session:
        session.add(EvaluationRow(id="stuck", config={}, config_hash="x", status="running", metrics={}, slices={}))
    assert fail_interrupted(eval_client.ctx) == 1
    listing = eval_client.get("/api/v1/evaluations", headers=HEADERS).json()
    assert {e["status"] for e in listing} == {"complete", "failed"}
    assert all("metrics" not in e for e in listing)
    stuck = eval_client.get("/api/v1/evaluations/stuck", headers=HEADERS).json()
    assert stuck["status"] == "failed" and "restart" in stuck["error"]
