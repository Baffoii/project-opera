"""GeoGuessr-style benchmark mode. These endpoints extend the V1 contract (see docs/API.md); nothing is stored."""
from __future__ import annotations

import random
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from ..context import AppContext
from ..eval.dataset import SPLITS, Dataset, DatasetError, list_dataset_ids, load_dataset, read_verified
from ..eval.metrics import geoguessr_style_score, great_circle_km
from ..services.pipeline import band_for, decide_status
from ..services.sanitize import UploadError, sanitize_image
from .deps import guard

router = APIRouter()


class LatLon(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class PlayRequest(BaseModel):
    dataset: str = Field(max_length=64)
    image_id: str = Field(max_length=64)
    model: str | None = Field(default=None, max_length=64)
    guess: LatLon | None = None


def _dataset(ctx: AppContext, dataset_id: str) -> Dataset:
    try:
        return load_dataset(ctx.settings.benchmark_dir, dataset_id)
    except DatasetError as exc:
        raise HTTPException(404 if "not found" in str(exc) else 400, str(exc)) from None


def _present(dataset: Dataset, item) -> bool:
    return dataset.image_path(item).is_file()


@router.get("/api/v1/benchmark/datasets")
def benchmark_datasets(ctx: AppContext = Depends(guard)) -> list[dict]:
    out = []
    for dataset_id in list_dataset_ids(ctx.settings.benchmark_dir):
        try:
            ds = load_dataset(ctx.settings.benchmark_dir, dataset_id)
        except DatasetError as exc:
            out.append({"id": dataset_id, "available": False, "reason": str(exc)})
            continue
        out.append(
            {
                "id": ds.id,
                "version": ds.version,
                "available": True,
                "image_source_types": sorted({i.image_source_type for i in ds.items}),
                "splits": {
                    split: {
                        "items": sum(i.split == split for i in ds.items),
                        "images_present": sum(i.split == split and _present(ds, i) for i in ds.items),
                    }
                    for split in SPLITS
                },
            }
        )
    return out


@router.get("/api/v1/benchmark/rounds")
def benchmark_rounds(
    dataset: str = Query(max_length=64),
    split: str = Query(default="heldout", max_length=16),
    n: int = Query(default=5, ge=1, le=50),
    seed: int = 0,
    ctx: AppContext = Depends(guard),
) -> dict:
    """Image ids for a game. Deliberately carries no coordinates, country or source details."""
    ds = _dataset(ctx, dataset)
    try:
        chosen = [i for i in ds.select(split, seed=seed) if _present(ds, i)]
    except DatasetError as exc:
        raise HTTPException(400, str(exc)) from None
    if not chosen:
        raise HTTPException(404, "No images of this split are present locally. Run scripts/fetch_benchmark.py.")
    random.Random(seed).shuffle(chosen)
    return {
        "dataset": ds.id,
        "dataset_version": ds.version,
        "split": split,
        "seed": seed,
        "rounds": [
            {"image_id": i.image_id, "image_url": f"/api/v1/benchmark/images/{ds.id}/{i.image_id}"}
            for i in chosen[:n]
        ],
    }


@router.get("/api/v1/benchmark/images/{dataset_id}/{image_id}")
def benchmark_image(dataset_id: str, image_id: str, ctx: AppContext = Depends(guard)) -> Response:
    ds = _dataset(ctx, dataset_id)
    item = next((i for i in ds.items if i.image_id == image_id), None)
    if item is None:
        raise HTTPException(404, "Image not found.")
    s = ctx.settings
    try:
        image = sanitize_image(read_verified(ds, item), max_bytes=s.max_upload_bytes, max_pixels=s.max_image_pixels)
    except (DatasetError, UploadError) as exc:
        raise HTTPException(404, getattr(exc, "message", str(exc))) from None
    return Response(
        image.data,
        media_type=image.mime,
        headers={"Cache-Control": "private, max-age=3600", "Content-Disposition": "inline"},
    )


def _model_result(ctx: AppContext, model_id: str, image, truth: tuple[float, float]) -> dict:
    s = ctx.settings
    adapter = ctx.geo_adapters.get(model_id)
    if adapter is None:
        raise HTTPException(400, f"Unknown model '{model_id}'.")
    base = {"id": adapter.id, "version": adapter.version, "kind": adapter.kind}
    ready, reason = adapter.availability()
    if not ready:
        return {**base, "status": "unavailable", "reason": reason, "candidates": []}
    started = time.perf_counter()
    try:
        geo = adapter.predict(image.data, image_sha256=image.sha256, top_k=5)
    except Exception:
        return {**base, "status": "failed", "reason": f"{adapter.id} failed.", "candidates": []}
    elapsed = (time.perf_counter() - started) * 1000 - geo.stages.get("model_load", 0.0)
    raw = sorted(geo.candidates, key=lambda c: c.score, reverse=True)[:5]
    status, reason = decide_status(raw, geo_error=None, clue_abstain=None, abstain_below=s.abstain_below_score)
    candidates = [
        {
            "rank": rank,
            "lat": c.lat,
            "lon": c.lon,
            "score": c.score,
            "confidence_band": band_for(c.score, s.band_high_at, s.band_medium_at),
            "uncalibrated": True,
            "error_km": round(great_circle_km(*truth, c.lat, c.lon), 1),
        }
        for rank, c in enumerate(raw, start=1)
    ]
    top1_error = candidates[0]["error_km"] if candidates else None
    return {
        **base,
        "status": status,
        "reason": reason,
        "abstained": status == "abstained",
        "candidates": candidates,
        "top1_error_km": top1_error,
        "score": None if status != "complete" or top1_error is None else geoguessr_style_score(top1_error),
        "latency_ms": round(max(elapsed, 0.0), 1),
    }


@router.post("/api/v1/benchmark/play")
def benchmark_play(body: PlayRequest, request: Request, ctx: AppContext = Depends(guard)) -> dict:
    """Reveal one round. The truth is returned only here, together with the image's attribution."""
    ds = _dataset(ctx, body.dataset)
    item = next((i for i in ds.items if i.image_id == body.image_id), None)
    if item is None:
        raise HTTPException(404, "Image not found.")
    model_id = body.model or ctx.settings.default_model
    request.state.model = model_id[:64]
    s = ctx.settings
    try:
        image = sanitize_image(read_verified(ds, item), max_bytes=s.max_upload_bytes, max_pixels=s.max_image_pixels)
    except (DatasetError, UploadError) as exc:
        raise HTTPException(404, getattr(exc, "message", str(exc))) from None
    truth = (item.lat, item.lon)
    user = None
    if body.guess is not None:
        error = round(great_circle_km(*truth, body.guess.lat, body.guess.lon), 1)
        user = {"guess": body.guess.model_dump(), "error_km": error, "score": geoguessr_style_score(error)}
    return {
        "dataset": ds.id,
        "dataset_version": ds.version,
        "image_id": item.image_id,
        "truth": {
            "lat": item.lat,
            "lon": item.lon,
            "country": item.country or None,
            "continent": item.continent or None,
            "settlement_type": item.settlement_type or None,
            "landscape": item.landscape or None,
            "image_source_type": item.image_source_type,
        },
        "attribution": {
            "license": item.license,
            "author": item.author,
            "source_url": item.source_url or None,
            "license_status": "needs_human_review",
        },
        "user": user,
        "model": _model_result(ctx, model_id, image, truth),
        "score_note": "Game score = 5000*exp(-km/1492.7). It is a game score, not a model metric.",
    }
