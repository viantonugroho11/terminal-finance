"""Metric resolvers — thin adapters over existing router capabilities.

Each function: (symbol) -> float. Async because provider calls are async.
Returns None if metric cannot be resolved (rule skipped, not fired).
"""
from __future__ import annotations

from collections.abc import Awaitable
from typing import Callable

from ..retry import with_retry


async def _quote_change_pct(symbol: str) -> float | None:
    from ..registry import router
    async def _fetch(p, s):
        return await with_retry(lambda: p.quote(s), provider=p.name, symbol=symbol)
    try:
        value, _, _ = await router.call(
            "quote", symbol=symbol, fetch=lambda p: _fetch(p, symbol),
        )
    except Exception:
        return None
    if not isinstance(value, dict):
        return None
    for k in ("change_pct", "changePercent", "regularMarketChangePercent"):
        v = value.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None


async def _volume_vs_ma20(symbol: str) -> float | None:
    from ..registry import router
    async def _fetch(p, s):
        return await with_retry(lambda: p.history(s, "3mo", "1d"),
                                provider=p.name, symbol=symbol)
    try:
        value, _, _ = await router.call(
            "history", symbol=symbol, fetch=lambda p: _fetch(p, symbol),
        )
    except Exception:
        return None
    candles = value.get("candles") if isinstance(value, dict) else value
    if not candles or len(candles) < 21:
        return None
    vols = [float(c.get("volume", 0)) for c in candles[-21:]]
    latest = vols[-1]
    ma20 = sum(vols[:-1]) / 20.0
    if ma20 <= 0:
        return None
    return latest / ma20


async def _foreign_net_flow(symbol: str) -> float | None:
    from ..registry import router
    async def _fetch(p, s):
        return await with_retry(lambda: p.foreign_flow(s),
                                provider=p.name, symbol=symbol)
    try:
        value, _, _ = await router.call(
            "foreign_flow", symbol=symbol, market="IDX",
            fetch=lambda p: _fetch(p, symbol),
        )
    except Exception:
        return None
    if isinstance(value, dict):
        return float(value.get("net_idr", 0.0))
    return None


async def _sentiment_spike(symbol: str) -> float | None:
    """Depends on news.store; late import to keep watch module standalone."""
    try:
        from ..news import store as nstore
    except Exception:
        return None
    return nstore.sentiment_score(symbol, window_hours=24)


RESOLVERS: dict[str, Callable[[str], Awaitable[float | None]]] = {
    "price_change_pct_intraday": _quote_change_pct,
    "price_change_pct_1d": _quote_change_pct,
    "volume_vs_ma20": _volume_vs_ma20,
    "foreign_net_flow_idr": _foreign_net_flow,
    "sentiment_spike": _sentiment_spike,
}


async def resolve(metric: str, symbol: str) -> float | None:
    fn = RESOLVERS.get(metric)
    if fn is None:
        return None
    return await fn(symbol)


def compare(op: str, value: float, threshold: float) -> bool:
    return {
        ">":  value >  threshold,
        "<":  value <  threshold,
        ">=": value >= threshold,
        "<=": value <= threshold,
        "==": value == threshold,
    }[op]
