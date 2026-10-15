from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select

from ..adapters.base import ClueAdapter
from ..context import AppContext
from ..db import EvaluationItemRow, EvaluationRow, session_scope, utcnow
from ..eval.country import CountryResolver, default_country_resolver
from ..eval.dataset import BenchmarkItem, Dataset, DatasetError, LeakageError, check_leakage, load_dataset
from ..eval.metrics import ItemResult
from ..eval.runner import EvalConfig, build_config, compute_outcome, evaluate_item
from .pipeline import estimate_vlm_cost

log = logging.getLogger("opera.eval")


class EvaluationRequestError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class _Plan:
    dataset: Dataset
    items: list[BenchmarkItem]
    config: EvalConfig
    clue_adapter: ClueAdapter | None
    resolver: CountryResolver | None
    notices: list[str]
    model_id: str


def plan_evaluation(
    ctx: AppContext,
    *,
    dataset_id: str,
    split: str,
    model_id: str,
    use_vlm_clues: bool,
    seed: int,
    limit: int | None,
) -> _Plan:
    s = ctx.settings
    try:
        dataset = load_dataset(s.benchmark_dir, dataset_id)
        items = dataset.select(split, seed=seed, limit=limit)
    except DatasetError as exc:
        raise EvaluationRequestError(404 if "not found" in str(exc) else 400, str(exc)) from None
    if not items:
        raise EvaluationRequestError(400, f"Split '{split}' of '{dataset_id}' has no items.")
    adapter = ctx.geo_adapters.get(model_id)
    if adapter is None:
        raise EvaluationRequestError(400, f"Unknown model '{model_id}'.")
    ready, reason = adapter.availability()
    if not ready:
        raise EvaluationRequestError(503, f"Model '{model_id}' is unavailable: {reason}")

    notices: list[str] = []
    clue_adapter: ClueAdapter | None = None
    if use_vlm_clues:
        real = ctx.clue_adapters.get("vlm-clues")
        ok, why = real.availability() if real else (False, "not registered")
        if ok:
            clue_adapter = real
        else:
            notices.append(f"VLM clues unavailable ({why}): evaluated without clues. Mock clues are never used in evaluation.")
    resolver = default_country_resolver()
    if resolver is None:
        notices.append("Country metrics skipped for candidates without a country: install the `eval` extra (reverse_geocoder).")
    config = build_config(
        s, dataset, adapter, split=split, use_vlm_clues=clue_adapter is not None, seed=seed, limit=limit, resolver=resolver
    )
    return _Plan(dataset, items, config, clue_adapter, resolver, notices, model_id)


def create_evaluation(ctx: AppContext, plan: _Plan) -> str:
    evaluation_id = uuid.uuid4().hex
    with session_scope(ctx.session_factory) as session:
        session.add(
            EvaluationRow(
                id=evaluation_id,
                config={**plan.config.to_dict(), "n_items_planned": len(plan.items)},
                config_hash=plan.config.hash,
                status="queued",
                metrics={},
                slices={},
            )
        )
    ctx.eval_executor.submit(run_evaluation, ctx, evaluation_id, plan)
    return evaluation_id


def _finish(ctx: AppContext, evaluation_id: str, **fields) -> None:
    with session_scope(ctx.session_factory) as session:
        row = session.get(EvaluationRow, evaluation_id)
        if row is None:
            return
        for key, value in fields.items():
            setattr(row, key, value)
        row.finished_at = utcnow()


def _store_item(ctx: AppContext, evaluation_id: str, result: ItemResult) -> None:
    with session_scope(ctx.session_factory) as session:
        session.add(
            EvaluationItemRow(
                evaluation_id=evaluation_id,
                image_id=result.image_id[:64],
                truth_lat=result.truth_lat,
                truth_lon=result.truth_lon,
                top1_lat=result.top1_lat,
                top1_lon=result.top1_lon,
                error_km=result.error_km,
                in_top5={
                    "failed": result.failed,
                    "top1_score": result.top1_score,
                    "top5_errors_km": result.top5_errors_km,
                    "within_km": {str(t): any(e <= t for e in result.top5_errors_km) for t in (1, 25, 200, 750)},
                    "truth_country": result.truth_country,
                    "top5_countries": result.top5_countries,
                },
                band=result.band,
                abstained=result.abstained,
                latency_ms=result.latency_ms,
                cost_usd=result.cost_usd,
            )
        )


def evaluate_plan(ctx: AppContext, plan: _Plan, on_item: Callable[[ItemResult], None] | None = None) -> list[ItemResult]:
    adapter = ctx.geo_adapters[plan.model_id]
    results: list[ItemResult] = []
    for item in plan.items:
        result = evaluate_item(
            ctx.settings,
            plan.dataset,
            item,
            adapter,
            clue_adapter=plan.clue_adapter,
            resolver=plan.resolver,
            price=lambda i, o: estimate_vlm_cost(ctx, i, o),
        )
        results.append(result)
        if on_item:
            on_item(result)
    return results


def run_evaluation(ctx: AppContext, evaluation_id: str, plan: _Plan) -> None:
    try:
        with session_scope(ctx.session_factory) as session:
            row = session.get(EvaluationRow, evaluation_id)
            row.status = "running"
            row.started_at = utcnow()
        # A held-out split is only meaningful if no image is shared with the seed split; refuse otherwise.
        try:
            check_leakage(plan.dataset)
        except LeakageError as exc:
            _finish(ctx, evaluation_id, status="failed", error=str(exc)[:500])
            return
        results = evaluate_plan(ctx, plan, on_item=lambda r: _store_item(ctx, evaluation_id, r))
        outcome = compute_outcome(results, plan.notices)
        _finish(ctx, evaluation_id, status="complete", metrics=outcome.metrics, slices=outcome.slices)
    except DatasetError as exc:
        _finish(ctx, evaluation_id, status="failed", error=str(exc)[:500])
    except Exception as exc:
        log.exception("evaluation %s crashed", evaluation_id)
        _finish(ctx, evaluation_id, status="failed", error=f"Evaluation crashed ({type(exc).__name__}).")


def fail_interrupted(ctx: AppContext) -> int:
    """Jobs that were queued or running when the process stopped will never finish; say so."""
    with session_scope(ctx.session_factory) as session:
        rows = session.scalars(select(EvaluationRow).where(EvaluationRow.status.in_(("queued", "running")))).all()
        for row in rows:
            row.status = "failed"
            row.error = "Interrupted by a backend restart."
            row.finished_at = utcnow()
        return len(rows)


def progress(ctx: AppContext, evaluation_id: str) -> int:
    with session_scope(ctx.session_factory) as session:
        return len(session.scalars(select(EvaluationItemRow.id).where(EvaluationItemRow.evaluation_id == evaluation_id)).all())
