from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .adapters.registry import build_clue_adapters, build_geo_adapters
from .config import Settings, get_settings
from .context import AppContext
from .geo.context_provider import NominatimProvider
from .db import init_db, make_engine, make_session_factory
from .routes import analyze, benchmark, evaluations, health
from .routes import registry as registry_routes
from .services import audit
from .services.evaluations import fail_interrupted
from .services.ratelimit import TokenBucketLimiter
from .services.storage import LocalStorage
from .services.sweeper import sweep_expired, sweep_loop

log = logging.getLogger("opera")
MULTIPART_OVERHEAD_BYTES = 1024 * 1024


def build_context(settings: Settings) -> AppContext:
    if settings.database_url.startswith("sqlite:///") and ":memory:" not in settings.database_url:
        from pathlib import Path

        Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.database_url)
    init_db(engine)
    return AppContext(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        storage=LocalStorage(settings.storage_dir),
        geo_adapters=build_geo_adapters(settings),
        clue_adapters=build_clue_adapters(settings),
        limiter=TokenBucketLimiter(settings.rate_limit_per_min, settings.rate_limit_burst),
        context_provider=NominatimProvider(settings) if settings.context_enabled else None,
    )


def create_app(settings: Settings | None = None, ctx: AppContext | None = None) -> FastAPI:
    settings = settings or get_settings()
    if ctx is None:
        ctx = build_context(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not settings.api_key:
            log.warning("OPERA_API_KEY is not set: every non-health route will answer 503.")
        await asyncio.to_thread(sweep_expired, ctx)
        await asyncio.to_thread(fail_interrupted, ctx)
        task = asyncio.create_task(sweep_loop(ctx))
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            ctx.eval_executor.shutdown(wait=False, cancel_futures=True)
            close = getattr(ctx.context_provider, "close", None)
            if close:
                close()

    app = FastAPI(title="OPERA backend", version="0.1.0", lifespan=lifespan)
    app.state.ctx = ctx

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = secrets.token_hex(8)
        request.state.request_id = request_id
        request.state.model = None
        request.state.client_hash = audit.hash_client(
            settings.audit_salt, request.client.host if request.client else None
        )
        length = request.headers.get("content-length")
        if (
            request.method == "POST"
            and length
            and length.isdigit()
            and int(length) > settings.max_upload_bytes + MULTIPART_OVERHEAD_BYTES
        ):
            response = JSONResponse({"detail": "Upload is too large."}, status_code=413)
        else:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        if request.url.path != "/api/health" and request.method != "OPTIONS":
            route = request.scope.get("route")
            endpoint = f"{request.method} {getattr(route, 'path', request.url.path)}"
            await run_in_threadpool(
                audit.record,
                ctx.session_factory,
                request_id=request_id,
                endpoint=endpoint,
                client_hash=request.state.client_hash,
                model=request.state.model,
                status=response.status_code,
            )
        return response

    # Added last so it is outermost: early 413/429 responses still carry CORS headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["X-OPERA-Key", "Content-Type"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )

    app.include_router(health.router)
    app.include_router(analyze.router)
    app.include_router(registry_routes.router)
    app.include_router(evaluations.router)
    app.include_router(benchmark.router)
    return app
