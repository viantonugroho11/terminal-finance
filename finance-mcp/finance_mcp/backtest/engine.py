"""Backtest event loop — deterministic, no look-ahead.

Fills execute at NEXT bar open (never same-bar close). All strategy
access to bars flows through BarContext which raises on future reads.
"""
from __future__ import annotations

from typing import Any

from . import costs, metrics
from .context import BarContext, Order, Position


def _apply_fill(portfolio: dict[str, Position], cash: float, *,
                symbol: str, side: str, qty: float, price: float,
                market: str) -> tuple[dict[str, Position], float, dict[str, Any]]:
    fp = costs.fill_price(base_price=price, side=side, market=market)
    notional = fp * qty
    fee = costs.transaction_cost(notional=notional, qty=qty, side=side,
                                 market=market)
    pos = portfolio.get(symbol) or Position(symbol=symbol)
    pnl = None
    if side.upper() == "BUY":
        cost = notional + fee
        new_qty = pos.qty + qty
        new_avg = ((pos.avg_price * pos.qty) + notional) / new_qty if new_qty > 0 else 0.0
        pos = Position(symbol=symbol, qty=new_qty, avg_price=new_avg)
        cash -= cost
    else:
        if qty > pos.qty + 1e-9:
            qty = pos.qty
            if qty <= 0:
                return portfolio, cash, {"skipped": True, "reason": "no_position"}
            notional = fp * qty
            fee = costs.transaction_cost(notional=notional, qty=qty, side=side,
                                         market=market)
        proceeds = notional - fee
        pnl = (fp - pos.avg_price) * qty - fee
        pos = Position(symbol=symbol, qty=pos.qty - qty, avg_price=pos.avg_price)
        cash += proceeds
    portfolio[symbol] = pos
    return portfolio, cash, {
        "symbol": symbol, "side": side, "qty": qty,
        "fill_price": fp, "fee": fee, "notional": notional, "pnl": pnl,
    }


def run(*, symbol: str, bars: list[dict[str, Any]],
        strategy_fn, params: dict[str, Any], market: str = "ID",
        initial_cash: float = 100_000_000.0) -> dict[str, Any]:
    """Deterministic bar-by-bar simulation.

    Contract:
      - bars sorted ascending by ts; each has open/high/low/close/volume.
      - strategy called at close of bar i; orders execute at open of i+1.
      - equity marked to current-bar close each step.
    """
    if not bars:
        raise ValueError("empty bar series")

    portfolio: dict[str, Position] = {}
    cash = initial_cash
    equity_curve: list[float] = []
    trade_log: list[dict[str, Any]] = []
    pending: list[Order] = []

    for i in range(len(bars)):
        bar = bars[i]

        # Fill pending orders at THIS bar's open.
        if pending:
            open_px = float(bar["open"])
            for order in pending:
                portfolio, cash, trade = _apply_fill(
                    portfolio, cash, symbol=order.symbol, side=order.side,
                    qty=order.qty, price=open_px, market=market,
                )
                trade["ts"] = str(bar.get("ts") or i)
                trade_log.append(trade)
            pending = []

        # Mark-to-market on this bar's close.
        close_px = float(bar["close"])
        mv = sum(p.qty * close_px for p in portfolio.values())
        equity_curve.append(cash + mv)

        # Ask strategy on this bar (past + current only).
        ctx = BarContext(
            symbol=symbol, _bars=bars, _index=i,
            portfolio=dict(portfolio), cash=cash,
        )
        new_orders = strategy_fn(ctx, params) or []
        # Validate: only accept symbols the engine tracks. v1 = single-symbol.
        for o in new_orders:
            if not isinstance(o, Order):
                raise TypeError(f"strategy returned non-Order: {o!r}")
        pending.extend(new_orders)

    return {
        "symbol": symbol,
        "market": market,
        "bars_count": len(bars),
        "equity_curve": equity_curve,
        "trades": trade_log,
        "final_positions": {s: p.__dict__ for s, p in portfolio.items()},
        "final_cash": cash,
        "metrics": metrics.summarize(equity_curve, trade_log),
    }
