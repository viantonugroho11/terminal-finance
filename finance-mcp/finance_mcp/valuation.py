"""Deterministic DCF and valuation math. Pure functions, no I/O.

Every formula uses standard textbook definitions. Reference-vector
tested in `tests/test_valuation.py`. See ADR-0013 (quant engine
contract) and ADR-0017 (DCF).

Nothing here calls a provider or reads config; the server tool assembles
inputs from `get_financial_statements` + `get_fundamentals` and hands
them to these functions.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

# ── Cost of capital ────────────────────────────────────────────────────

def capm(risk_free: float, beta: float, equity_risk_premium: float) -> float:
    """Cost of equity via CAPM. All inputs as decimals (0.045 = 4.5%)."""
    return risk_free + beta * equity_risk_premium


def wacc(
    cost_of_equity: float,
    cost_of_debt: float,
    tax_rate: float,
    equity_weight: float,
    debt_weight: float,
) -> float:
    """Weighted-average cost of capital. Weights must sum to 1.0 (±1e-6)."""
    if abs(equity_weight + debt_weight - 1.0) > 1e-6:
        raise ValueError(
            f"equity_weight + debt_weight must == 1.0, got "
            f"{equity_weight + debt_weight:.6f}"
        )
    if not 0.0 <= tax_rate <= 1.0:
        raise ValueError(f"tax_rate must be in [0,1], got {tax_rate}")
    return (equity_weight * cost_of_equity
            + debt_weight * cost_of_debt * (1.0 - tax_rate))


# ── Growth / projection ────────────────────────────────────────────────

def cagr(values: Sequence[float]) -> float | None:
    """Compound annual growth rate across a series (oldest → newest)."""
    if len(values) < 2:
        return None
    start, end = values[0], values[-1]
    if start <= 0 or end <= 0:
        return None
    n = len(values) - 1
    return (end / start) ** (1.0 / n) - 1.0


def project_fcf(base_fcf: float, growth_rate: float, years: int) -> list[float]:
    """Project FCF forward at a constant growth rate. Years >= 1."""
    if years < 1:
        raise ValueError("years must be >= 1")
    return [base_fcf * ((1.0 + growth_rate) ** i) for i in range(1, years + 1)]


# ── Terminal value + DCF ───────────────────────────────────────────────

def terminal_value_gordon(fcf_last: float, terminal_growth: float,
                          discount_rate: float) -> float:
    """Gordon growth model. Requires discount_rate > terminal_growth."""
    if discount_rate <= terminal_growth:
        raise ValueError(
            "discount_rate must exceed terminal_growth "
            f"({discount_rate} vs {terminal_growth})"
        )
    return fcf_last * (1.0 + terminal_growth) / (discount_rate - terminal_growth)


def npv(cashflows: Sequence[float], discount_rate: float,
        start_period: int = 1) -> float:
    """Present value of a cashflow series discounted at a flat rate.

    start_period=1 discounts the first CF one period, matching DCF
    convention (end-of-year cashflows).
    """
    total = 0.0
    for i, cf in enumerate(cashflows):
        t = start_period + i
        total += cf / ((1.0 + discount_rate) ** t)
    return total


@dataclass
class DcfResult:
    projected_fcf: list[float]
    discount_rate: float
    terminal_growth: float
    pv_explicit: float           # PV of the explicit projection period
    terminal_value: float        # nominal terminal value at year N
    pv_terminal: float           # PV of terminal value
    enterprise_value: float      # pv_explicit + pv_terminal
    equity_value: float | None   # EV − net debt (if net_debt supplied)
    per_share_value: float | None
    assumptions: dict = field(default_factory=dict)


def dcf(
    base_fcf: float,
    growth_rate: float,
    years: int,
    discount_rate: float,
    terminal_growth: float,
    *,
    net_debt: float | None = None,
    shares_outstanding: float | None = None,
) -> DcfResult:
    """Standard two-stage DCF (explicit projection + Gordon terminal).

    Args are all decimals for rates. Terminal value discounted from year N.
    """
    if years < 1:
        raise ValueError("years must be >= 1")
    projected = project_fcf(base_fcf, growth_rate, years)
    pv_explicit = npv(projected, discount_rate, start_period=1)
    tv = terminal_value_gordon(projected[-1], terminal_growth, discount_rate)
    pv_tv = tv / ((1.0 + discount_rate) ** years)
    ev = pv_explicit + pv_tv
    equity = (ev - net_debt) if net_debt is not None else None
    per_share = (equity / shares_outstanding
                 if (equity is not None and shares_outstanding
                     and shares_outstanding > 0) else None)
    return DcfResult(
        projected_fcf=projected,
        discount_rate=discount_rate,
        terminal_growth=terminal_growth,
        pv_explicit=pv_explicit,
        terminal_value=tv,
        pv_terminal=pv_tv,
        enterprise_value=ev,
        equity_value=equity,
        per_share_value=per_share,
        assumptions={
            "base_fcf": base_fcf, "growth_rate": growth_rate, "years": years,
            "net_debt": net_debt, "shares_outstanding": shares_outstanding,
        },
    )


# ── Sensitivity table ──────────────────────────────────────────────────

def sensitivity_table(
    base_fcf: float,
    growth_rate: float,
    years: int,
    discount_rates: Sequence[float],
    terminal_growths: Sequence[float],
    *,
    net_debt: float | None = None,
    shares_outstanding: float | None = None,
) -> dict:
    """Grid of per-share value (or EV if no shares) over WACC × g_terminal."""
    rows: list[dict] = []
    for r in discount_rates:
        row = {"discount_rate": r, "cells": []}
        for g in terminal_growths:
            if r <= g:
                row["cells"].append({"terminal_growth": g, "value": None,
                                     "note": "r must exceed g"})
                continue
            res = dcf(base_fcf, growth_rate, years, r, g,
                      net_debt=net_debt, shares_outstanding=shares_outstanding)
            row["cells"].append({
                "terminal_growth": g,
                "value": (res.per_share_value if shares_outstanding
                          else res.enterprise_value),
            })
        rows.append(row)
    return {
        "unit": "per_share" if shares_outstanding else "enterprise_value",
        "rows": rows,
    }


# ── Reverse DCF ────────────────────────────────────────────────────────

def implied_growth(
    current_price: float,
    base_fcf_per_share: float,
    years: int,
    discount_rate: float,
    terminal_growth: float,
    *,
    tolerance: float = 1e-4,
    max_iter: int = 100,
) -> float | None:
    """Growth rate that makes DCF per-share == current_price.

    Bisection on growth in [-0.20, +0.60]. Returns None if the market
    price can't be explained inside that band.
    """
    def _pv_per_share(g: float) -> float:
        proj = project_fcf(base_fcf_per_share, g, years)
        pv = npv(proj, discount_rate, start_period=1)
        tv = terminal_value_gordon(proj[-1], terminal_growth, discount_rate)
        return pv + tv / ((1.0 + discount_rate) ** years)

    lo, hi = -0.20, 0.60
    f_lo, f_hi = _pv_per_share(lo) - current_price, _pv_per_share(hi) - current_price
    if f_lo * f_hi > 0:
        return None  # price lies outside the bracketed band
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        f_mid = _pv_per_share(mid) - current_price
        if abs(f_mid) < tolerance:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0
