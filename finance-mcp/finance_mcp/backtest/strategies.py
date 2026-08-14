"""Named strategies registry — deterministic, no external deps."""
from __future__ import annotations
from typing import Any, Callable

from .context import BarContext, Order


Strategy = Callable[[BarContext, dict[str, Any]], list[Order]]


def buy_and_hold(ctx: BarContext, params: dict[str, Any]) -> list[Order]:
    """One BUY on first bar, then hold. `size` = shares to buy."""
    if ctx._index != 0:
        return []
    size = float(params.get("size", 100))
    return [Order(symbol=ctx.symbol, side="BUY", qty=size)]


def sma_cross(ctx: BarContext, params: dict[str, Any]) -> list[Order]:
    """SMA fast/slow cross. `fast`, `slow`, `size` in params.

    On golden cross (fast crossing above slow) → BUY if flat.
    On death cross (fast crossing below slow) → SELL if long.
    """
    fast_n = int(params.get("fast", 20))
    slow_n = int(params.get("slow", 50))
    size = float(params.get("size", 100))
    if ctx._index < slow_n:
        return []
    window = ctx.prices(lookback=slow_n + 1)
    if len(window) < slow_n + 1:
        return []
    closes = [b["close"] for b in window]
    prev_fast = sum(closes[-(fast_n + 1):-1]) / fast_n
    prev_slow = sum(closes[-(slow_n + 1):-1]) / slow_n
    cur_fast = sum(closes[-fast_n:]) / fast_n
    cur_slow = sum(closes[-slow_n:]) / slow_n
    pos = ctx.position(ctx.symbol)
    if prev_fast <= prev_slow and cur_fast > cur_slow and pos.qty == 0:
        return [Order(symbol=ctx.symbol, side="BUY", qty=size)]
    if prev_fast >= prev_slow and cur_fast < cur_slow and pos.qty > 0:
        return [Order(symbol=ctx.symbol, side="SELL", qty=pos.qty)]
    return []


def mean_revert(ctx: BarContext, params: dict[str, Any]) -> list[Order]:
    """Buy at close < MA(N) - k*std, sell at close > MA(N) + k*std."""
    n = int(params.get("window", 20))
    k = float(params.get("k", 2.0))
    size = float(params.get("size", 100))
    if ctx._index < n:
        return []
    window = ctx.prices(lookback=n)
    closes = [b["close"] for b in window]
    mean = sum(closes) / n
    var = sum((c - mean) ** 2 for c in closes) / n
    sd = var ** 0.5
    price = ctx.bar["close"]
    pos = ctx.position(ctx.symbol)
    if price < mean - k * sd and pos.qty == 0:
        return [Order(symbol=ctx.symbol, side="BUY", qty=size)]
    if price > mean + k * sd and pos.qty > 0:
        return [Order(symbol=ctx.symbol, side="SELL", qty=pos.qty)]
    return []


REGISTRY: dict[str, Strategy] = {
    "buy_and_hold": buy_and_hold,
    "sma_cross": sma_cross,
    "mean_revert": mean_revert,
}


def get(name: str) -> Strategy:
    if name not in REGISTRY:
        raise KeyError(f"unknown strategy: {name!r}. Known: {sorted(REGISTRY)}")
    return REGISTRY[name]
