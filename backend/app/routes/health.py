from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text

from ..context import AppContext
from .deps import get_ctx

router = APIRouter()


@router.get("/api/health")
def health(ctx: AppContext = Depends(get_ctx)) -> dict:
    try:
        with ctx.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db = "ok"
    except Exception:
        db = "error"
    storage = "ok" if ctx.storage.healthy() else "error"
    adapters: dict[str, str] = {}
    notes: dict[str, str] = {}
    providers = [ctx.context_provider] if ctx.context_provider else []
    for adapter in [*ctx.geo_adapters.values(), *ctx.clue_adapters.values(), *providers]:
        ready, reason = adapter.availability()
        adapters[adapter.id] = "ready" if ready else "unavailable"
        if not ready and reason:
            notes[adapter.id] = reason
    return {
        "status": "ok" if db == "ok" and storage == "ok" else "degraded",
        "db": db,
        "storage": storage,
        "adapters": adapters,
        "adapter_notes": notes,
    }
