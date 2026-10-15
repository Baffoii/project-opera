"""Command-line evaluation. Examples (from backend/):

    python -m app.eval.cli run --dataset opera-commons-v1 --split heldout --model geoclip-v1
    python -m app.eval.cli calibrate --dataset opera-commons-v1 --model geoclip-v1 --out /tmp/calibration.json
"""
from __future__ import annotations

import argparse
import json
import sys

from ..config import get_settings
from ..main import build_context
from ..services.evaluations import EvaluationRequestError, evaluate_plan, plan_evaluation
from .calibration import calibrate
from .dataset import LeakageError, check_leakage
from .runner import compute_outcome


def _run(ctx, args, split, settings_override=None):
    if settings_override:
        ctx.settings = ctx.settings.model_copy(update=settings_override)
    plan = plan_evaluation(
        ctx,
        dataset_id=args.dataset,
        split=split,
        model_id=args.model,
        use_vlm_clues=args.clues,
        seed=args.seed,
        limit=args.limit,
    )
    results = evaluate_plan(ctx, plan)
    outcome = compute_outcome(results, plan.notices)
    return plan, results, outcome


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.eval.cli")
    parser.add_argument("command", choices=("run", "calibrate"))
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--split", default="heldout", choices=("seed", "heldout", "all"))
    parser.add_argument("--model", default=None)
    parser.add_argument("--clues", action="store_true", help="include real VLM clues (needs OPENAI_API_KEY)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", default=None, help="write the JSON report here as well as to stdout")
    args = parser.parse_args(argv)
    settings = get_settings()
    args.model = args.model or settings.default_model
    ctx = build_context(settings)
    try:
        plan_check = plan_evaluation(
            ctx, dataset_id=args.dataset, split="all", model_id=args.model, use_vlm_clues=False, seed=0, limit=None
        )
        check_leakage(plan_check.dataset)
        if args.command == "run":
            plan, results, outcome = _run(ctx, args, args.split)
            report = {"config": plan.config.to_dict(), "config_hash": plan.config.hash, "metrics": outcome.metrics, "slices": outcome.slices}
        else:
            plan, seed_results, seed_outcome = _run(ctx, args, "seed")
            fitted = calibrate(seed_results)
            chosen = {k: v for k, v in fitted["thresholds"].items() if v is not None}
            _, _, heldout_before = _run(ctx, args, "heldout")
            _, _, heldout_after = _run(ctx, args, "heldout", chosen)
            report = {
                "fitted_on": "seed",
                "calibration": fitted,
                "provisional_thresholds": plan.config.thresholds,
                "seed_metrics_provisional": seed_outcome.metrics["overall"],
                "heldout_with_provisional": heldout_before.metrics["overall"],
                "heldout_with_calibrated": heldout_after.metrics["overall"],
            }
    except (EvaluationRequestError, LeakageError) as exc:
        print(f"error: {getattr(exc, 'message', exc)}", file=sys.stderr)
        return 2
    text = json.dumps(report, indent=2, sort_keys=True, default=str)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
