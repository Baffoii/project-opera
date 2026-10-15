from __future__ import annotations

import hashlib
import logging

from sqlalchemy.orm import sessionmaker

from ..db import AuditLogRow, session_scope

log = logging.getLogger("opera.audit")


def hash_client(salt: str, client_host: str | None) -> str:
    """Salted hash of the client address; the raw address is never stored."""
    return hashlib.sha256(f"{salt}:{client_host or 'unknown'}".encode()).hexdigest()[:32]


def record(
    factory: sessionmaker,
    *,
    request_id: str,
    endpoint: str,
    client_hash: str,
    model: str | None,
    status: int,
) -> None:
    """Request metadata only. Never pass image bytes, filenames or anything derived from the image."""
    try:
        with session_scope(factory) as session:
            session.add(
                AuditLogRow(
                    request_id=request_id,
                    endpoint=endpoint[:120],
                    client_hash=client_hash,
                    model=model,
                    status=status,
                )
            )
    except Exception:  # auditing must never take the request down
        log.exception("audit write failed")
