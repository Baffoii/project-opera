from __future__ import annotations

import threading
import time
from collections.abc import Callable


class TokenBucketLimiter:
    """In-memory token bucket per client key. Single-process only (documented limitation)."""

    def __init__(
        self,
        per_minute: float,
        burst: int,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.rate = per_minute / 60.0
        self.burst = max(1, burst)
        self._clock = clock
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[float, float]] = {}

    def acquire(self, key: str) -> tuple[bool, float]:
        """Returns (allowed, retry_after_seconds)."""
        now = self._clock()
        with self._lock:
            tokens, last = self._buckets.get(key, (float(self.burst), now))
            tokens = min(float(self.burst), tokens + (now - last) * self.rate)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                return True, 0.0
            self._buckets[key] = (tokens, now)
            retry = (1.0 - tokens) / self.rate if self.rate > 0 else 60.0
            return False, retry
