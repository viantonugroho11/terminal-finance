#!/usr/bin/env python3
"""ADR-0027 migration: copy running-avg transactions → synthetic lots.

Idempotent: skips symbols that already have any lot rows.

Usage:
    FINANCE_DB=/path/to/finance.db python3 scripts/migrate_portfolio_v1_to_v2.py
"""
from __future__ import annotations
import sys
from datetime import datetime, timezone

from finance_mcp.portfolio import db as pdb, lots as plots

pdb.init()
plots.init()


def _existing_symbols() -> set[str]:
    with pdb.connect() as conn:
        rows = conn.execute("SELECT DISTINCT symbol FROM lots").fetchall()
    return {r["symbol"] for r in rows}


def _running_avg_positions() -> list[tuple[str, float, float, str]]:
    """Return (symbol, qty, avg_cost, first_buy_iso) from `transactions`."""
    with pdb.connect() as conn:
        rows = conn.execute(
            "SELECT symbol, side, quantity, price, fee, currency, executed_at "
            "FROM transactions ORDER BY executed_at ASC"
        ).fetchall()
    acc: dict[str, dict] = {}
    for r in rows:
        s = r["symbol"].upper()
        side = r["side"]
        pos = acc.setdefault(s, {"qty": 0.0, "cost": 0.0, "first": None,
                                 "currency": r["currency"] or "IDR"})
        if side == "BUY":
            pos["qty"] += r["quantity"]
            pos["cost"] += r["quantity"] * r["price"] + (r["fee"] or 0.0)
            if pos["first"] is None:
                pos["first"] = r["executed_at"]
        elif side == "SELL":
            if pos["qty"] > 0:
                avg = pos["cost"] / pos["qty"]
                take = min(pos["qty"], r["quantity"])
                pos["cost"] -= avg * take
                pos["qty"] -= take
    out = []
    for s, v in acc.items():
        if v["qty"] > 0:
            avg = v["cost"] / v["qty"]
            first = v["first"] or datetime.now(timezone.utc).isoformat()
            out.append((s, v["qty"], avg, first, v["currency"]))
    return out


def main() -> int:
    already = _existing_symbols()
    migrated = 0
    skipped = 0
    for sym, qty, avg, first, ccy in _running_avg_positions():
        if sym in already:
            skipped += 1
            continue
        lot = plots.Lot(
            symbol=sym, qty=qty, price=avg, acquired_at=first,
            currency=ccy or "IDR",
            note="migrated from v1 running-avg transactions",
        )
        plots.record_buy(lot)
        migrated += 1
    print(f"migrated={migrated} skipped={skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
