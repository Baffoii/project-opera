from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from .adapters.base import ClueAdapter, GeoAdapter
from .config import Settings
from .geo.context_provider import ContextProvider
from .services.ratelimit import TokenBucketLimiter
from .services.storage import Storage


@dataclass
class AppContext:
    settings: Settings
    engine: Engine
    session_factory: sessionmaker
    storage: Storage
    geo_adapters: dict[str, GeoAdapter]
    clue_adapters: dict[str, ClueAdapter]
    limiter: TokenBucketLimiter
    context_provider: ContextProvider | None = None
