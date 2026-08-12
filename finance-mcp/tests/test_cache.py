import asyncio
import time
import pytest
from finance_mcp.cache import TTLCache


def test_set_get_hit():
    c = TTLCache()
    c.set("k", 42, ttl_seconds=5)
    assert c.get("k") == 42
    assert c.stats()["hits"] == 1


def test_miss():
    c = TTLCache()
    assert c.get("nope") is None
    assert c.stats()["misses"] == 1


def test_ttl_expiry(monkeypatch):
    c = TTLCache()
    c.set("k", 1, ttl_seconds=0.05)
    time.sleep(0.1)
    assert c.get("k") is None


def test_zero_ttl_is_noop():
    c = TTLCache()
    c.set("k", 1, ttl_seconds=0)
    assert c.get("k") is None


def test_get_or_fetch_populates():
    c = TTLCache()
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        return "value"

    v1, hit1 = asyncio.run(c.get_or_fetch("k", 5, fetch))
    v2, hit2 = asyncio.run(c.get_or_fetch("k", 5, fetch))
    assert v1 == v2 == "value"
    assert hit1 is False and hit2 is True
    assert calls == 1


def test_get_or_fetch_dedupes_concurrent():
    c = TTLCache()
    calls = 0

    async def slow_fetch():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return "v"

    async def run():
        # 10 concurrent requests → only 1 fetch
        return await asyncio.gather(*(c.get_or_fetch("k", 5, slow_fetch) for _ in range(10)))

    results = asyncio.run(run())
    assert all(r[0] == "v" for r in results)
    assert calls == 1


def test_invalidate():
    c = TTLCache()
    c.set("k", 1, 5)
    c.invalidate("k")
    assert c.get("k") is None
    c.set("a", 1, 5); c.set("b", 2, 5)
    c.invalidate()
    assert c.stats()["size"] == 0
