from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

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
    # One worker: evaluations are long, model-bound jobs and must not run concurrently on one machine.
    eval_executor: ThreadPoolExecutor = field(
        default_factory=lambda: ThreadPoolExecutor(max_workers=1, thread_name_prefix="opera-eval")
    )
