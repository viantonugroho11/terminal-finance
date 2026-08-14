"""Rebalance plan — deterministic weight-diff (ADR-0027).

Note: ADR proposed LP via scipy.optimize.linprog; a simple weight-diff
algorithm is used here to avoid a heavy dep for v1. Output is still
deterministic and unit-testable; upgrade to LP is a drop-in.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from . import lots as _lots
from . import tax as _tax


@dataclass
class Trade:
    symbol: str
    side: str            # BUY | SELL
    qty: float
    notional: float
    tax_cost: float
    reason: str


def rebalance_plan(
    *,
    targets: dict[str, float],
    quotes: dict[str, float],
    account: str = "main",
    tolerance: float = 0.02,
    regime: str = "ID",
    cash: float = 0.0,
) -> dict[str, Any]:
    """Compute trades to move weights within `tolerance` of `targets`.

    Positions come from the lot store. `quotes` supplies current prices.
    `cash` is included in total portfolio value (used to sink under-
    allocation). Tax cost is estimated per sell using `regime`.

    Deterministic algorithm:
      1. Sum market value across held symbols + cash.
      2. For each target symbol, compute target notional.
      3. Diff vs current notional; skip if |drift| within tolerance.
      4. Emit BUY / SELL trades with integer share rounding.
    """
    if abs(sum(targets.values()) - 1.0) > 1e-3:
        raise ValueError("targets must sum to 1.0")

    pos = _lots.positions(account)
    current_notional: dict[str, float] = {}
    total = cash
    for sym, p in pos.items():
        price = quotes.get(sym) or 0.0
        n = price * p["qty"]
        current_notional[sym] = n
        total += n

    for sym in targets:
        current_notional.setdefault(sym, 0.0)

    trades: list[Trade] = []
    for sym, w in sorted(targets.items()):
        price = quotes.get(sym)
        if not price or price <= 0:
            continue
        target_notional = w * total
        cur = current_notional.get(sym, 0.0)
        drift = target_notional - cur
        drift_pct = abs(drift) / total if total > 0 else 0.0
        if drift_pct < tolerance:
            continue
        qty = drift / price
        side = "BUY" if qty > 0 else "SELL"
        qty_abs = abs(qty)
        notional = qty_abs * price
        tax_cost = 0.0
        if side == "SELL":
            tax_cost = _tax.tax_on_sell(
                asset_class=_asset_class(sym), gross_proceeds=notional,
                regime=regime,
            )
        else:
            tax_cost = _tax.tax_on_buy(
                asset_class=_asset_class(sym), gross_cost=notional,
                regime=regime,
            )
        trades.append(Trade(
            symbol=sym, side=side, qty=qty_abs, notional=notional,
            tax_cost=tax_cost,
            reason=(f"drift {drift_pct*100:.2f}% > tolerance "
                    f"{tolerance*100:.2f}%"),
        ))

    return {
        "account": account,
        "regime": regime,
        "total_portfolio_value": total,
        "cash": cash,
        "tolerance": tolerance,
        "trades": [t.__dict__ for t in trades],
        "total_tax_cost": sum(t.tax_cost for t in trades),
    }


def _asset_class(symbol: str) -> str:
    if symbol.upper() in {"BTC", "ETH", "USDT", "USDC", "SOL", "BNB"}:
        return "CRYPTO"
    if symbol.upper().endswith(".JK") or len(symbol) == 4:
        return "EQUITY_ID"
    return "EQUITY_US"
