"""PnL calc over lot store (ADR-0027).

Pure functions. Never depend on live prices — caller passes `quotes`.
"""
from __future__ import annotations

from typing import Any

from . import lots as _lots
from . import tax as _tax


def unrealized_pnl(quotes: dict[str, float],
                   account: str = "main") -> dict[str, Any]:
    """quotes: {symbol → last_price}. Missing symbols get null price."""
    pos = _lots.positions(account)
    rows = []
    total_mv = 0.0
    total_cost = 0.0
    total_pnl = 0.0
    for sym, p in pos.items():
        price = quotes.get(sym)
        mv = (price * p["qty"]) if price is not None else None
        pnl = (mv - p["cost_basis"]) if mv is not None else None
        rows.append({
            "symbol": sym,
            "qty": p["qty"],
            "avg_price": p["avg_price"],
            "cost_basis": p["cost_basis"],
            "price": price,
            "market_value": mv,
            "unrealized_pnl": pnl,
            "unrealized_pnl_pct": (pnl / p["cost_basis"] * 100.0
                                   if pnl is not None and p["cost_basis"] > 0
                                   else None),
        })
        if mv is not None:
            total_mv += mv
        total_cost += p["cost_basis"]
        if pnl is not None:
            total_pnl += pnl
    return {
        "account": account,
        "positions": rows,
        "total_market_value": total_mv,
        "total_cost_basis": total_cost,
        "total_unrealized_pnl": total_pnl,
    }


def realized_pnl(account: str = "main",
                 regime: str = "ID") -> dict[str, Any]:
    """Sum realized PnL from closes, per symbol + after-tax under regime.

    Each close matches to a single lot (its `lot_id`); realized = qty *
    (sell_price - lot.price) - fees on that close - tax on that close.
    Regime tax is recomputed here on gross proceeds using ADR rates,
    so callers do not need to have recorded tax on the sell itself.
    """
    closes = _lots.list_closes(account=account)
    with_lots = _index_lots_by_id(account)
    per_symbol: dict[str, dict[str, float]] = {}
    for c in closes:
        lot = with_lots.get(c["lot_id"])
        if lot is None:
            continue
        sym = lot["symbol"]
        gross = c["qty"] * c["price"]
        cost = c["qty"] * lot["price"]
        fee = float(c.get("fee") or 0.0)
        tax_recorded = float(c.get("tax") or 0.0)
        tax_regime = _tax.tax_on_sell(
            asset_class=_asset_class(sym), gross_proceeds=gross, regime=regime,
        )
        pnl_gross = gross - cost - fee
        pnl_after_tax = pnl_gross - tax_regime
        acc = per_symbol.setdefault(sym, {
            "qty_closed": 0.0, "gross_proceeds": 0.0,
            "cost_basis": 0.0, "fees": 0.0,
            "tax_recorded": 0.0, "tax_regime": 0.0,
            "pnl_gross": 0.0, "pnl_after_tax": 0.0,
        })
        acc["qty_closed"] += c["qty"]
        acc["gross_proceeds"] += gross
        acc["cost_basis"] += cost
        acc["fees"] += fee
        acc["tax_recorded"] += tax_recorded
        acc["tax_regime"] += tax_regime
        acc["pnl_gross"] += pnl_gross
        acc["pnl_after_tax"] += pnl_after_tax
    rows = [{"symbol": s, **v} for s, v in per_symbol.items()]
    totals = {
        k: sum(r[k] for r in rows)
        for k in ("gross_proceeds", "cost_basis", "fees",
                  "tax_recorded", "tax_regime", "pnl_gross", "pnl_after_tax")
    }
    return {"account": account, "regime": regime.upper(),
            "positions": rows, "totals": totals}


def _index_lots_by_id(account: str) -> dict[str, dict[str, Any]]:
    all_ = _lots.list_lots(open_only=False, account=account)
    return {l["id"]: l for l in all_}


def _asset_class(symbol: str) -> str:
    if symbol.upper() in {"BTC", "ETH", "USDT", "USDC", "SOL", "BNB"}:
        return "CRYPTO"
    if symbol.upper().endswith(".JK") or len(symbol) == 4:
        return "EQUITY_ID"
    return "EQUITY_US"
