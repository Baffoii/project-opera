from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

from .conftest import ANALYZE_FORM, HEADERS, analyze_files, make_ctx, make_settings


def test_health_is_open_and_reports_components(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["db"] == "ok" and body["storage"] == "ok"
    assert body["adapters"]["mock"] == "ready"
    assert body["adapters"]["geoclip-v1"] == "unavailable"
    assert body["adapters"]["vlm-clues"] == "unavailable"
    assert body["adapter_notes"]["vlm-clues"]


def test_non_health_routes_require_key(client, jpeg_bytes):
    for method, path in [
        ("get", "/api/v1/models"),
        ("get", "/api/v1/datasets"),
        ("get", "/api/v1/analyses/abc"),
        ("delete", "/api/v1/analyses/abc"),
    ]:
        assert getattr(client, method)(path).status_code == 401, path
    r = client.post("/api/v1/analyze", files=analyze_files(jpeg_bytes()), data=ANALYZE_FORM)
    assert r.status_code == 401
    r = client.get("/api/v1/models", headers={"X-OPERA-Key": "wrong"})
    assert r.status_code == 401
    assert client.get("/api/v1/models", headers=HEADERS).status_code == 200


def test_non_ascii_key_does_not_crash(client):
    r = client.get("/api/v1/models", headers={"X-OPERA-Key": "ключ".encode()})
    assert r.status_code == 401


def test_fails_closed_when_no_key_configured(tmp_path):
    s = make_settings(tmp_path, api_key="")
    with TestClient(create_app(s, make_ctx(s))) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/v1/models", headers=HEADERS).status_code == 503
        assert c.get("/api/v1/models").status_code == 503


def test_rate_limit_returns_429_with_retry_after(tmp_path):
    s = make_settings(tmp_path, rate_limit_per_min=1, rate_limit_burst=3)
    with TestClient(create_app(s, make_ctx(s))) as c:
        codes = [c.get("/api/v1/models", headers=HEADERS).status_code for _ in range(5)]
        assert codes[:3] == [200, 200, 200]
        assert codes[3:] == [429, 429]
        limited = c.get("/api/v1/models", headers=HEADERS)
        assert int(limited.headers["Retry-After"]) >= 1
        assert c.get("/api/health").status_code == 200  # health is never limited


def test_cors_only_allows_configured_origin(client):
    ok = client.options(
        "/api/v1/models",
        headers={"Origin": "http://localhost:4173", "Access-Control-Request-Method": "GET"},
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:4173"
    bad = client.options(
        "/api/v1/models",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in bad.headers


def test_registry_endpoints_label_license_review(client):
    models = client.get("/api/v1/models", headers=HEADERS).json()
    by_id = {m["id"]: m for m in models}
    assert by_id["mock"]["available"] is True and by_id["mock"]["kind"] == "mock"
    assert by_id["geoclip-v1"]["available"] is False
    assert by_id["geoclip-v1"]["license_status"] == "needs_human_review"
    datasets = client.get("/api/v1/datasets", headers=HEADERS).json()
    assert {d["id"] for d in datasets} >= {"gods-eye-view", "geoclip", "osv-5m", "openstreetmap", "google-maps-earth"}
    assert all(d["license_status"] == "needs_human_review" for d in datasets)
    assert all(set(d["rights"]) == {"display", "evaluation", "fine_tuning", "redistribution"} for d in datasets)
