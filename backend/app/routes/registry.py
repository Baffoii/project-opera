from __future__ import annotations

from fastapi import APIRouter, Depends

from ..context import AppContext
from ..registry import load_datasets, load_models
from .deps import guard

router = APIRouter()


@router.get("/api/v1/models")
def list_models(ctx: AppContext = Depends(guard)) -> list[dict]:
    adapters = {**ctx.geo_adapters, **ctx.clue_adapters}
    out = []
    for entry in load_models(ctx.settings.registry_dir):
        adapter = adapters.get(entry["id"])
        ready, reason = adapter.availability() if adapter else (False, "no adapter registered")
        out.append(
            {
                **entry,
                "version": getattr(adapter, "version", entry.get("version")) if adapter else entry.get("version"),
                "available": ready,
                "unavailable_reason": None if ready else reason,
            }
        )
    return out


@router.get("/api/v1/datasets")
def list_datasets(ctx: AppContext = Depends(guard)) -> list[dict]:
    return load_datasets(ctx.settings.registry_dir)
