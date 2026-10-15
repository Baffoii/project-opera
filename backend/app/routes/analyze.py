from __future__ import annotations

import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..context import AppContext
from ..db import AnalysisRow, UploadRow, session_scope, utcnow
from ..schemas import Analysis
from ..services.pipeline import analysis_from_row, run_analysis
from ..services.sanitize import UploadError, sanitize_image
from .deps import guard

router = APIRouter()


@router.post("/api/v1/analyze", response_model=Analysis)
def analyze(
    request: Request,
    image: UploadFile = File(...),
    model: str | None = Form(default=None),
    use_vlm_clues: bool = Form(default=False),
    metadata_free: bool = Form(default=True),
    rights_attested: bool = Form(default=False),
    ctx: AppContext = Depends(guard),
) -> Analysis:
    model_id = model or ctx.settings.default_model
    request.state.model = model_id[:64]
    if not rights_attested:
        raise HTTPException(422, "rights_attested must be true: confirm you have the right to analyze this image.")
    adapter = ctx.geo_adapters.get(model_id)
    if adapter is None:
        raise HTTPException(400, f"Unknown model '{model_id}'.")
    ready, reason = adapter.availability()
    if not ready:
        raise HTTPException(503, f"Model '{model_id}' is unavailable: {reason}")

    t = time.perf_counter()
    data = image.file.read(ctx.settings.max_upload_bytes + 1)
    timings = {"read": round((time.perf_counter() - t) * 1000, 2)}
    t = time.perf_counter()
    try:
        sanitized = sanitize_image(
            data, max_bytes=ctx.settings.max_upload_bytes, max_pixels=ctx.settings.max_image_pixels
        )
    except UploadError as exc:
        raise HTTPException(exc.status, exc.message) from None
    timings["sanitize"] = round((time.perf_counter() - t) * 1000, 2)
    return run_analysis(
        ctx,
        sanitized,
        model_id=model_id,
        use_vlm_clues=use_vlm_clues,
        metadata_free=metadata_free,
        timings=timings,
    )


def _load(ctx: AppContext, session, analysis_id: str) -> AnalysisRow:
    row = session.scalar(
        select(AnalysisRow).where(AnalysisRow.id == analysis_id).options(selectinload(AnalysisRow.candidates))
    )
    if row is None or row.expires_at <= utcnow():
        raise HTTPException(404, "Analysis not found.")
    return row


@router.get("/api/v1/analyses/{analysis_id}", response_model=Analysis)
def get_analysis(analysis_id: str, ctx: AppContext = Depends(guard)) -> Analysis:
    with session_scope(ctx.session_factory) as session:
        return analysis_from_row(_load(ctx, session, analysis_id))


@router.delete("/api/v1/analyses/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: str, ctx: AppContext = Depends(guard)) -> Response:
    with session_scope(ctx.session_factory) as session:
        row = session.get(AnalysisRow, analysis_id)
        if row is None:
            raise HTTPException(404, "Analysis not found.")
        upload = session.get(UploadRow, row.upload_id)
        if upload is not None:
            ctx.storage.delete(upload.storage_key)
            session.delete(upload)  # cascades to analyses and candidates
        else:
            session.delete(row)
    return Response(status_code=204)
