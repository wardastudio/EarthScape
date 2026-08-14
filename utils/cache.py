from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Optional


class TTLCache:
    def __init__(self, max_size: int = 1000, default_ttl: int = 300) -> None:
        self._cache: "OrderedDict[str, tuple[Any, float]]" = OrderedDict()
        self._lock = threading.Lock()
        self._max_size = max_size
        self._default_ttl = default_ttl

    def _is_expired(self, expires_at: float) -> bool:
        return time.time() > expires_at

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                return None
            value, expires_at = self._cache[key]
            if self._is_expired(expires_at):
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        expires_at = time.time() + ttl
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (value, expires_at)
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def has(self, key: str) -> bool:
        with self._lock:
            if key not in self._cache:
                return False
            _, expires_at = self._cache[key]
            if self._is_expired(expires_at):
                del self._cache[key]
                return False
            return True

    def size(self) -> int:
        with self._lock:
            self._purge_expired()
            return len(self._cache)

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [k for k, (_, exp) in self._cache.items() if now > exp]
        for k in expired:
            del self._cache[k]


class CacheManager:
    def __init__(self) -> None:
        self.caches: dict[str, TTLCache] = {}

    def get_cache(self, name: str, max_size: int = 1000, default_ttl: int = 300) -> TTLCache:
        if name not in self.caches:
            self.caches[name] = TTLCache(max_size=max_size, default_ttl=default_ttl)
        return self.caches[name]

    def clear_all(self) -> None:
        for cache in self.caches.values():
            cache.clear()


cache_manager = CacheManager()


def get_or_create(
    cache: TTLCache,
    key: str,
    factory: Callable[[], Any],
    ttl: Optional[int] = None,
) -> tuple[Any, bool]:
    cached = cache.get(key)
    if cached is not None:
        return cached, True
    value = factory()
    cache.set(key, value, ttl=ttl)
    return value, False


def make_key(*parts: Any) -> str:
    return ":".join(str(p).lower().strip() if p is not None else "" for p in parts)
