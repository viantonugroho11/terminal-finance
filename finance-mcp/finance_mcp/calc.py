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


# ── ADR-0031: FX forward via covered interest parity ──────────────

def fx_forward_via_cip(*, spot: float, rate_dom_annual: float,
                       rate_for_annual: float, tenor_days: int,
                       day_count: int = 360) -> tuple[float, float]:
    """Return (forward_rate, forward_points).

    CIP for a spot quoted as DOM per FOR (e.g. USDIDR: IDR per USD):
      F = S * (1 + r_dom * t) / (1 + r_for * t)
    where r_* are the deposit rates over tenor.

    Rates are annualized decimals (0.06 = 6%). Simple interest with
    configurable day count (360 for money market convention).
    """
    if spot <= 0 or tenor_days < 0 or day_count <= 0:
        raise ValueError("invalid inputs")
    t = tenor_days / day_count
    fwd = spot * (1.0 + rate_dom_annual * t) / (1.0 + rate_for_annual * t)
    return fwd, fwd - spot
