from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Dict

from config import Config
from utils.errors import RateLimitError


class RateLimiter:
    def __init__(self) -> None:
        self._requests: Dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()
        self._default_limit = Config.RATE_LIMIT
        self._default_window = 60

    def check(self, key: str, limit: int | None = None, window: int | None = None) -> bool:
        limit = limit if limit is not None else self._default_limit
        window = window if window is not None else self._default_window
        now = time.time()
        with self._lock:
            timestamps = self._requests[key]
            timestamps[:] = [ts for ts in timestamps if now - ts < window]
            if len(timestamps) >= limit:
                return False
            timestamps.append(now)
            return True

    def remaining(self, key: str, limit: int | None = None, window: int | None = None) -> int:
        limit = limit if limit is not None else self._default_limit
        window = window if window is not None else self._default_window
        now = time.time()
        with self._lock:
            timestamps = self._requests[key]
            timestamps[:] = [ts for ts in timestamps if now - ts < window]
            return max(0, limit - len(timestamps))

    def reset(self, key: str) -> None:
        with self._lock:
            self._requests.pop(key, None)

    def enforce(self, key: str, limit: int | None = None, window: int | None = None) -> None:
        if not self.check(key, limit=limit, window=window):
            raise RateLimitError(
                message="Too many requests, please try again later.",
                details={"limit": limit or self._default_limit, "window": window or self._default_window},
            )


rate_limiter = RateLimiter()
