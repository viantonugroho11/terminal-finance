"""Backtest result metrics — pure functions."""
from __future__ import annotations
import math
from typing import Any


def _returns(equity: list[float]) -> list[float]:
    out = []
    for i in range(1, len(equity)):
        prev = equity[i - 1]
        if prev == 0:
            out.append(0.0)
        else:
            out.append((equity[i] - prev) / prev)
    return out


def total_return(equity: list[float]) -> float:
    if not equity or equity[0] == 0:
        return 0.0
    return (equity[-1] - equity[0]) / equity[0]


def max_drawdown(equity: list[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        if peak > 0:
            dd = min(dd, (v - peak) / peak)
    return dd


def sharpe(equity: list[float], *, periods_per_year: int = 252,
           risk_free_rate: float = 0.0) -> float | None:
    r = _returns(equity)
    if len(r) < 2:
        return None
    rf_per = risk_free_rate / periods_per_year
    excess = [x - rf_per for x in r]
    mean = sum(excess) / len(excess)
    var = sum((x - mean) ** 2 for x in excess) / (len(excess) - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return None
    return mean / sd * math.sqrt(periods_per_year)


def sortino(equity: list[float], *, periods_per_year: int = 252) -> float | None:
    r = _returns(equity)
    if len(r) < 2:
        return None
    downs = [x for x in r if x < 0]
    if not downs:
        return None
    mean = sum(r) / len(r)
    dvar = sum(x ** 2 for x in downs) / len(downs)
    dsd = math.sqrt(dvar)
    if dsd == 0:
        return None
    return mean / dsd * math.sqrt(periods_per_year)


def hit_rate(trades: list[dict[str, Any]]) -> float | None:
    closed = [t for t in trades if t.get("pnl") is not None]
    if not closed:
        return None
    wins = sum(1 for t in closed if t["pnl"] > 0)
    return wins / len(closed)


def summarize(equity: list[float], trades: list[dict[str, Any]],
              *, periods_per_year: int = 252) -> dict[str, Any]:
    return {
        "final_equity": equity[-1] if equity else 0.0,
        "total_return": total_return(equity),
        "max_drawdown": max_drawdown(equity),
        "sharpe": sharpe(equity, periods_per_year=periods_per_year),
        "sortino": sortino(equity, periods_per_year=periods_per_year),
        "trades_count": len(trades),
        "hit_rate": hit_rate(trades),
    }
