from __future__ import annotations

import logging
import secrets
import time
from datetime import timedelta

from ..adapters.base import ClueError, RawCandidate
from ..context import AppContext
from ..db import AnalysisRow, CandidateRow, UploadRow, session_scope, utcnow
from ..schemas import Analysis, Candidate, Clue
from .sanitize import SanitizedImage

log = logging.getLogger("opera.pipeline")

# Heuristic radii per band until M5 calibration exists. They are NOT measured error statistics.
UNCERTAINTY_KM = {"high": 25.0, "medium": 150.0, "low": 750.0}
PIPELINE_VERSION = "pipeline-0.1"


def band_for(score: float, high_at: float, medium_at: float) -> str:
    if score >= high_at:
        return "high"
    if score >= medium_at:
        return "medium"
    return "low"


def analysis_from_row(row: AnalysisRow) -> Analysis:
    return Analysis(
        id=row.id,
        status=row.status,
        abstain_reason=row.abstain_reason,
        model_kind=row.model_kind,
        clues_kind=row.clues_kind,
        clues=[Clue(**c) for c in row.clues],
        clue_model_region_guesses=row.region_guesses,
        candidates=[
            Candidate(
                rank=c.rank,
                lat=c.lat,
                lon=c.lon,
                label=c.label,
                country_code=c.country_code,
                score=c.score,
                confidence_band=c.confidence_band,
                uncalibrated=c.uncalibrated,
                uncertainty_km=c.uncertainty_km,
                source_model=c.source_model,
            )
            for c in row.candidates
        ],
        versions=row.versions,
        provenance=row.provenance,
        notices=row.notices,
        latency_ms=row.latency,
        cost_estimate_usd=row.cost,
        created_at=row.created_at,
        expires_at=row.expires_at,
    )


def _cost(ctx: AppContext, input_tokens: int | None, output_tokens: int | None) -> float | None:
    s = ctx.settings
    if input_tokens is None or output_tokens is None:
        return None
    if s.vlm_price_input_per_mtok <= 0 and s.vlm_price_output_per_mtok <= 0:
        return None  # no price configured: report null rather than guess
    return round(
        input_tokens / 1e6 * s.vlm_price_input_per_mtok + output_tokens / 1e6 * s.vlm_price_output_per_mtok, 6
    )


def run_analysis(
    ctx: AppContext,
    image: SanitizedImage,
    *,
    model_id: str,
    use_vlm_clues: bool,
    metadata_free: bool,
    timings: dict[str, float],
) -> Analysis:
    s = ctx.settings
    adapter = ctx.geo_adapters[model_id]
    notices: list[str] = []
    provenance: list[dict] = []
    latency: dict[str, float] = dict(timings)

    if not metadata_free:
        notices.append("metadata_free=false was ignored: OPERA always strips EXIF/XMP/IPTC before analysis.")

    t = time.perf_counter()
    storage_key = ctx.storage.put(image.data)
    latency["store"] = round((time.perf_counter() - t) * 1000, 2)

    try:
        t = time.perf_counter()
        geo = adapter.predict(image.data, image_sha256=image.sha256, top_k=5)
        latency["geolocate"] = round((time.perf_counter() - t) * 1000, 2)
        for stage, ms in geo.stages.items():
            latency[stage] = round(ms, 2)
        versions_extra = dict(geo.notes)
        geo_error = None
    except Exception as exc:
        log.warning("geo adapter %s failed: %s", adapter.id, type(exc).__name__)
        geo, geo_error, versions_extra = None, f"{adapter.id} failed ({type(exc).__name__}).", {}

    clues: list[dict] = []
    region_guesses: list[dict] = []
    clues_kind = "none"
    clue_abstain: str | None = None
    cost: float | None = None
    versions: dict = {
        "pipeline": PIPELINE_VERSION,
        "geo_adapter": f"{adapter.id}@{adapter.version}",
        "uncertainty": "band-heuristic-v0",
    }
    versions.update(versions_extra)
    if use_vlm_clues:
        real = ctx.clue_adapters.get("vlm-clues")
        ready, reason = real.availability() if real else (False, "not registered")
        clue_adapter = real if ready else ctx.clue_adapters.get("mock-clues")
        if not ready:
            if clue_adapter is not None:
                notices.append(f"VLM clues unavailable ({reason}): showing MOCK clues that are not about this image.")
            else:
                notices.append(f"VLM clues unavailable: {reason}.")
        if clue_adapter is not None:
            try:
                t = time.perf_counter()
                result = clue_adapter.extract(image.data, mime=image.mime)
                latency["clues"] = round((time.perf_counter() - t) * 1000, 2)
                clues = result.clues
                region_guesses = [{"region": g} for g in result.region_guesses]
                clues_kind = clue_adapter.kind
                cost = _cost(ctx, result.input_tokens, result.output_tokens)
                notices.extend(result.notices)
                if result.abstain:
                    clue_abstain = result.abstain_reason or "no reason given"
                    notices.append(f"Clue model abstained: {clue_abstain}")
                versions["clue_adapter"] = f"{clue_adapter.id}@{clue_adapter.version}"
                versions["prompt"] = result.prompt_version
                versions["clue_model"] = result.model_name
                if clue_adapter.kind == "real":
                    provenance.append({"provider": "openai", "role": "clues", "attribution": None})
                    if result.input_tokens is not None:
                        versions["clue_tokens"] = {"input": result.input_tokens, "output": result.output_tokens}
            except Exception as exc:
                log.warning("clue adapter failed: %s", type(exc).__name__)
                detail = str(exc) if isinstance(exc, ClueError) else type(exc).__name__
                notices.append(f"VLM clues failed ({detail}); geolocation continued without them.")

    raw: list[RawCandidate] = list(geo.candidates)[:5] if geo else []
    raw.sort(key=lambda c: c.score, reverse=True)
    status = "complete"
    abstain_reason: str | None = None
    if geo_error:
        status, abstain_reason = "failed", geo_error
    elif not raw:
        status, abstain_reason = "abstained", "The model returned no candidates."
    elif clue_abstain and clues_kind == "real":
        status = "abstained"
        abstain_reason = f"The clue model found no usable geographic content: {clue_abstain}"
    elif raw[0].score < s.abstain_below_score:
        status = "abstained"
        abstain_reason = "Top raw score is below the abstention threshold; the model is not confident enough to suggest places."

    now = utcnow()
    expires = now + timedelta(hours=s.upload_ttl_hours)
    analysis_id = secrets.token_hex(12)
    provenance.append(
        {"provider": adapter.id, "role": "candidates", "kind": adapter.kind, "version": adapter.version, "attribution": None}
    )

    t = time.perf_counter()
    with session_scope(ctx.session_factory) as session:
        upload = UploadRow(
            id=secrets.token_hex(12),
            storage_key=storage_key,
            sha256=image.sha256,
            phash=image.phash,
            mime=image.mime,
            bytes=len(image.data),
            created_at=now,
            expires_at=expires,
        )
        row = AnalysisRow(
            id=analysis_id,
            upload=upload,
            status=status,
            abstain_reason=abstain_reason,
            model_kind=adapter.kind,
            clues_kind=clues_kind,
            versions=versions,
            clues=clues,
            region_guesses=region_guesses,
            provenance=provenance,
            notices=notices,
            latency=dict(latency),
            cost=cost,
            created_at=now,
            expires_at=expires,
        )
        if status == "complete":
            for rank, c in enumerate(raw, start=1):
                band = band_for(c.score, s.band_high_at, s.band_medium_at)
                row.candidates.append(
                    CandidateRow(
                        rank=rank,
                        lat=c.lat,
                        lon=c.lon,
                        label=c.label,
                        country_code=c.country_code,
                        score=c.score,
                        confidence_band=band,
                        uncalibrated=True,
                        uncertainty_km=UNCERTAINTY_KM[band],
                        source_model=f"{adapter.id}@{adapter.version}",
                    )
                )
        session.add(upload)
        session.add(row)
        session.flush()
        persisted = {**latency, "persist": round((time.perf_counter() - t) * 1000, 2)}
        persisted["total"] = round(sum(persisted.values()), 2)
        row.latency = persisted  # a new dict, so the JSON column change is detected
        result = analysis_from_row(row)
    return result
