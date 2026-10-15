from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from ..context import AppContext
from ..db import UploadRow, session_scope, utcnow

log = logging.getLogger("opera.sweeper")


def sweep_expired(ctx: AppContext, now: datetime | None = None) -> int:
    """Delete expired uploads (file first, then rows; analyses and candidates cascade)."""
    now = now or utcnow()
    removed = 0
    with session_scope(ctx.session_factory) as session:
        for upload in session.scalars(select(UploadRow).where(UploadRow.expires_at <= now)).all():
            try:
                ctx.storage.delete(upload.storage_key)
            except ValueError:
                log.warning("skipping file delete for malformed storage key")
            session.delete(upload)
            removed += 1
    return removed


async def sweep_loop(ctx: AppContext) -> None:
    while True:
        try:
            count = await asyncio.to_thread(sweep_expired, ctx)
            if count:
                log.info("sweeper removed %d expired upload(s)", count)
        except Exception:
            log.exception("sweeper pass failed")
        await asyncio.sleep(ctx.settings.sweep_interval_s)
