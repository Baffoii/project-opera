# OPERA API

Base path `/api`, JSON unless noted. The machine-readable schema is `docs/openapi.json`
(regenerate with `cd backend && .venv/bin/python scripts/export_openapi.py`); a running backend also serves it
at `/openapi.json`. This page adds the behaviour the schema cannot express, with real example output.

## Authentication, limits, errors

- Every route except `GET /api/health` needs the header `X-OPERA-Key: <OPERA_API_KEY>`. With no key configured the
  backend fails closed: non-health routes answer `503`. A wrong or missing key answers `401`.
- Requests are rate limited per client (`OPERA_RATE_LIMIT_PER_MIN`, default 30): `429` with `Retry-After`.
- Errors are `{"detail": "<message>"}`. Messages never contain file contents, paths or secrets.
- Analyses are private: reachable only with the API key and the analysis id, deleted after `OPERA_UPLOAD_TTL_HOURS`
  (default 24) or on `DELETE`.

## Endpoints

| Method and path | Purpose |
| --- | --- |
| `GET /api/health` | Database, storage and per-adapter readiness. No key needed. |
| `POST /api/v1/analyze` | Multipart upload, returns the analysis. |
| `GET /api/v1/analyses/{id}` | Fetch a stored analysis (404 once deleted or expired). |
| `DELETE /api/v1/analyses/{id}` | Delete image file and rows (204). |
| `GET /api/v1/models` | Registered models with `kind` (`mock`/`real`), licence status, availability. |
| `GET /api/v1/datasets` | Source registry (`backend/registry/datasets.yaml`). |
| `POST /api/v1/evaluations` | Start a background evaluation run (202, `{"evaluation_id"}`). |
| `GET /api/v1/evaluations` | List runs (no metrics). |
| `GET /api/v1/evaluations/{id}` | Status, config, config hash, progress, metrics, slices. |
| `GET /api/v1/benchmark/datasets` | Benchmark datasets present locally. |
| `GET /api/v1/benchmark/rounds` | Metadata-free rounds for the game (no coordinates). |
| `GET /api/v1/benchmark/images/{dataset}/{image}` | The round image, re-encoded without metadata. |
| `POST /api/v1/benchmark/play` | Submit an optional guess, get truth, model prediction and scores. |

The two `/benchmark` groups and the `evaluations` listing are additions to the contract in `OPERA_V1_BUILD.md` (see D-log).

## `POST /api/v1/analyze`

Form fields: `image` (file; JPEG, PNG or WebP, checked by magic bytes), `model` (optional id, default
`OPERA_DEFAULT_MODEL`), `use_vlm_clues` (bool, default false), `metadata_free` (bool, default true),
`rights_attested` (must be `true`, else `422`). Oversize files or too many pixels answer `413`, a wrong type `415`, an undecodable or empty file `400`; an unknown model
`400`; a model that is registered but cannot run (missing weights, no key) `503` with the reason.

The image is decoded and re-encoded server-side, which drops EXIF/XMP/IPTC/GPS, before anything else sees it.

```
curl -s -H "X-OPERA-Key: $OPERA_API_KEY" -F image=@photo.jpg -F rights_attested=true \
     -F model=geoclip-v1 -F use_vlm_clues=false http://127.0.0.1:8000/api/v1/analyze
```

Example (mock model, output shortened to two candidates). `model_kind: "mock"` means placeholder data, not a prediction:

```json
{
  "id": "2684bc577757f0c07437b2b6",
  "status": "complete",
  "abstain_reason": null,
  "model_kind": "mock",
  "clues_kind": "none",
  "clues": [],
  "clue_model_region_guesses": [],
  "candidates": [
    {"rank": 1, "lat": -22.9068, "lon": -43.1729, "label": "MOCK: Rio de Janeiro", "country_code": "BR",
     "score": 0.6759, "confidence_band": "high", "uncalibrated": true, "uncertainty_km": 25.0,
     "source_model": "mock@mock-0.1", "context": null},
    {"rank": 2, "lat": -33.8688, "lon": 151.2093, "label": "MOCK: Sydney", "country_code": "AU",
     "score": 0.4055, "confidence_band": "high", "uncalibrated": true, "uncertainty_km": 25.0,
     "source_model": "mock@mock-0.1", "context": null}
  ],
  "versions": {"pipeline": "pipeline-0.1", "geo_adapter": "mock@mock-0.1", "uncertainty": "band-heuristic-v0"},
  "provenance": [{"provider": "mock", "role": "candidates", "kind": "mock", "version": "mock-0.1", "attribution": null}],
  "notices": [],
  "latency_ms": {"read": 0.0, "sanitize": 206.98, "store": 0.21, "geolocate": 0.02, "persist": 3.02, "total": 210.23},
  "cost_estimate_usd": null,
  "created_at": "2026-10-15T09:34:33.643167Z",
  "expires_at": "2026-10-16T09:34:33.643167Z"
}
```

Reading the response:

- `score` is a raw model output, **not a probability**. Scores from different models are never averaged or merged.
  Every candidate carries `uncalibrated: true`; `confidence_band` and `uncertainty_km` come from thresholds, not from
  a per-image error estimate (see `versions.uncertainty`).
- `status` is `complete`, `abstained` (top score below the abstention threshold, or the VLM saw nothing usable;
  `abstain_reason` says which) or `failed`. An abstained analysis still returns whatever candidates exist.
- `clues` are VLM observations (`observed` vs `speculative`); `clue_model_region_guesses` are the VLM's own region guesses,
  kept apart from `candidates` and never used to rank them. `clues_kind` is `real`, `mock` or `none`.
- `candidates[].context` holds the OSM Nominatim place name when available (`status`: `ok`, `cached`, `stale`,
  `no_result`, `unavailable`); `provenance` lists OSM attribution only when a place name was actually used.

## Evaluations

`POST /api/v1/evaluations` body: `{"dataset": "opera-synthetic-v1", "split": "heldout", "model": "mock",
"use_vlm_clues": false, "seed": 0, "limit": null}` (`split` is `seed`, `heldout` or `all`; `limit` 1..10000 picks a seeded
subset). Errors: `404` dataset not found, `400` invalid, `503` model unavailable. The run is queued on a single worker.
If the VLM is unavailable the run proceeds without clues and says so in `metrics.notices`; mock clues are never used.

`GET /api/v1/evaluations/{id}` returns `status` (`queued`, `running`, `complete`, `failed`), `error`, `config` (dataset id
and version, split, model and version, `use_vlm_clues`, seed, limit, thresholds, country resolver), `config_hash`,
`items_done`/`items_total`, `metrics`, `slices`, timestamps. A run fails (with the pairs listed in `error`) if images are
shared between the `seed` and `heldout` splits (exact SHA-256 or perceptual-hash Hamming distance <= 6).

`metrics` has `overall` and `by_image_source_type` (street-view-style and user-contributed-style images are never pooled
into one headline), each with `all` (ignores abstention) and `answered` (abstained items removed): `median_km`, `mean_km`,
`within_km` (1, 25, 200, 750), `top5_within_km`, `country_accuracy`, `top5_country_recall`, plus `abstention_rate`,
`reliability` (observed top-1 hit rate within 200 km per confidence band) and `ops` (p50/p95 latency, cost). Slices cover
country, continent, settlement type, landscape and image source type. `reproducible_hash` covers everything except `ops`:
the same dataset version, model version, seed and config give the same hash.

## Benchmark game

`GET /api/v1/benchmark/rounds?dataset=&split=&n=&seed=` returns rounds containing only `image_id` and an image URL.
`POST /api/v1/benchmark/play` with `{"dataset", "image_id", "model", "guess": {"lat","lon"} | null}` returns the truth,
attribution (`license`, `author`, `source_url`, `license_status`: `needs_human_review` until a person has read the licence),
the user's `error_km` and `score`, and the model's candidates with per-candidate `error_km`. The score is the GeoGuessr-style
game score `5000 * exp(-d / 1492.7)`: a game score, not a model metric.
