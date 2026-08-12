"""In-memory TTL cache. Provider calls are rate-limited — cache aggressively but
honor configured TTL. Not a distributed cache; sidecar process only.
"""
from __future__ import annotations
import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Hashable


@dataclass
class _Entry:
    value: Any
    expires_at: float


class TTLCache:
    def __init__(self) -> None:
        self._store: dict[Hashable, _Entry] = {}
        self._locks: dict[Hashable, asyncio.Lock] = {}
        self._hits = 0
        self._misses = 0

    def _lock_for(self, key: Hashable) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    def get(self, key: Hashable) -> Any | None:
        e = self._store.get(key)
        if e is None:
            self._misses += 1
            return None
        if e.expires_at < time.monotonic():
            self._store.pop(key, None)
            self._misses += 1
            return None
        self._hits += 1
        return e.value

    def set(self, key: Hashable, value: Any, ttl_seconds: float) -> None:
        if ttl_seconds <= 0:
            return
        self._store[key] = _Entry(value, time.monotonic() + ttl_seconds)

    async def get_or_fetch(self, key: Hashable, ttl_seconds: float,
                           fetch: Callable[[], Awaitable[Any]]) -> tuple[Any, bool]:
        """Returns (value, cache_hit)."""
        hit = self.get(key)
        if hit is not None:
            return hit, True
        async with self._lock_for(key):
            hit = self.get(key)
            if hit is not None:
                return hit, True
            value = await fetch()
            self.set(key, value, ttl_seconds)
            return value, False

    def stats(self) -> dict[str, int]:
        return {"hits": self._hits, "misses": self._misses, "size": len(self._store)}

    def invalidate(self, key: Hashable | None = None) -> None:
        if key is None:
            self._store.clear()
        else:
            self._store.pop(key, None)


# TTL config from env with sane defaults; skills/tools read these constants.
def _ttl(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


TTL_QUOTE          = _ttl("FINANCE_CACHE_TTL_QUOTE",          15)      # 15s
TTL_HISTORY        = _ttl("FINANCE_CACHE_TTL_HISTORY",        300)     # 5m
TTL_COMPANY        = _ttl("FINANCE_CACHE_TTL_COMPANY",        21600)   # 6h
TTL_FUNDAMENTALS   = _ttl("FINANCE_CACHE_TTL_FUNDAMENTALS",   21600)   # 6h
TTL_STATEMENTS     = _ttl("FINANCE_CACHE_TTL_STATEMENTS",     21600)   # 6h
TTL_NEWS           = _ttl("FINANCE_CACHE_TTL_NEWS",           300)     # 5m
TTL_MARKET         = _ttl("FINANCE_CACHE_TTL_MARKET",         60)      # 1m
TTL_MOVERS         = _ttl("FINANCE_CACHE_TTL_MOVERS",         120)     # 2m

cache = TTLCache()
