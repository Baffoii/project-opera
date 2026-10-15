from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..context import AppContext
from ..db import EvaluationRow, session_scope
from ..services import evaluations as svc
from .deps import guard

router = APIRouter()


class EvaluationRequest(BaseModel):
    dataset: str = Field(max_length=64)
    split: str = Field(default="heldout", max_length=16)
    model: str | None = Field(default=None, max_length=64)
    use_vlm_clues: bool = False
    seed: int = 0
    limit: int | None = Field(default=None, ge=1, le=10_000)


def _view(ctx: AppContext, row: EvaluationRow) -> dict:
    config = dict(row.config or {})
    total = config.pop("n_items_planned", None)
    return {
        "evaluation_id": row.id,
        "status": row.status,
        "error": row.error,
        "config": config,
        "config_hash": row.config_hash,
        "items_done": svc.progress(ctx, row.id),
        "items_total": total,
        "metrics": row.metrics or None,
        "slices": row.slices or None,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
    }


@router.post("/api/v1/evaluations", status_code=202)
def start_evaluation(body: EvaluationRequest, request: Request, ctx: AppContext = Depends(guard)) -> dict:
    model_id = body.model or ctx.settings.default_model
    request.state.model = model_id[:64]
    try:
        plan = svc.plan_evaluation(
            ctx,
            dataset_id=body.dataset,
            split=body.split,
            model_id=model_id,
            use_vlm_clues=body.use_vlm_clues,
            seed=body.seed,
            limit=body.limit,
        )
    except svc.EvaluationRequestError as exc:
        raise HTTPException(exc.status, exc.message) from None
    return {"evaluation_id": svc.create_evaluation(ctx, plan)}


@router.get("/api/v1/evaluations")
def list_evaluations(ctx: AppContext = Depends(guard)) -> list[dict]:
    with session_scope(ctx.session_factory) as session:
        rows = session.scalars(select(EvaluationRow).order_by(EvaluationRow.started_at.desc().nullslast()).limit(50)).all()
        return [
            {k: v for k, v in _view(ctx, r).items() if k not in ("metrics", "slices")} for r in rows
        ]


@router.get("/api/v1/evaluations/{evaluation_id}")
def get_evaluation(evaluation_id: str, ctx: AppContext = Depends(guard)) -> dict:
    with session_scope(ctx.session_factory) as session:
        row = session.get(EvaluationRow, evaluation_id)
        if row is None:
            raise HTTPException(404, "Evaluation not found.")
        return _view(ctx, row)
