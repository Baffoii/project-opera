from __future__ import annotations

import secrets as _secrets

from fastapi import Depends, Header, HTTPException, Request

from ..context import AppContext
from ..services.audit import hash_client


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def guard(
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    x_opera_key: str | None = Header(default=None, alias="X-OPERA-Key"),
) -> AppContext:
    """Rate limit first (so key guessing is throttled), then require the API key. Fails closed with no key set."""
    client = hash_client(ctx.settings.audit_salt, request.client.host if request.client else None)
    request.state.client_hash = client
    allowed, retry_after = ctx.limiter.acquire(client)
    if not allowed:
        raise HTTPException(429, "Rate limit exceeded.", headers={"Retry-After": str(max(1, int(retry_after + 0.999)))})
    if not ctx.settings.api_key:
        raise HTTPException(503, "Server has no OPERA_API_KEY configured.")
    if not x_opera_key or not _secrets.compare_digest(x_opera_key.encode(), ctx.settings.api_key.encode()):
        raise HTTPException(401, "Missing or invalid X-OPERA-Key.")
    return ctx
