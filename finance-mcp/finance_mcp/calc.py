"""Deterministic financial calculations. LLM never does this arithmetic."""
from __future__ import annotations
from typing import Iterable


def percentage_change(old: float, new: float) -> float | None:
    if old == 0 or old is None or new is None:
        return None
    return (new - old) / old * 100.0


def simple_return(entry: float, exit: float) -> float | None:
    if entry == 0 or entry is None or exit is None:
        return None
    return (exit - entry) / entry


def average(values: Iterable[float]) -> float | None:
    xs = [v for v in values if v is not None]
    return sum(xs) / len(xs) if xs else None


def weighted_average(values: Iterable[float], weights: Iterable[float]) -> float | None:
    vs = list(values); ws = list(weights)
    if len(vs) != len(ws) or not vs:
        return None
    pairs = [(v, w) for v, w in zip(vs, ws) if v is not None and w is not None]
    total_w = sum(w for _, w in pairs)
    if total_w == 0:
        return None
    return sum(v * w for v, w in pairs) / total_w


def market_cap(shares_outstanding: float | None, price: float | None) -> float | None:
    if shares_outstanding is None or price is None:
        return None
    return shares_outstanding * price


def enterprise_value(market_cap_: float | None, total_debt: float | None,
                     cash: float | None) -> float | None:
    if market_cap_ is None:
        return None
    return market_cap_ + (total_debt or 0.0) - (cash or 0.0)


def cagr(start: float, end: float, years: float) -> float | None:
    if start is None or end is None or start <= 0 or years <= 0 or end <= 0:
        return None
    return (end / start) ** (1.0 / years) - 1.0
