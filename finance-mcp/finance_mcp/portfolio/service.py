"""Portfolio calc — deterministic. Never ask LLM to sum holdings.

Router-driven: IDX tickers (BBCA, BBRI, TLKM, …) automatically price
via the IDX provider in IDR; US tickers (AAPL, NVDA) via Yahoo in USD.
Position dataclass carries the quote currency so downstream
`portfolio_summary` can group by currency instead of naively summing
mixed-currency market values.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from ..registry import routed_company, routed_history, routed_quote
from . import db


@dataclass
class Position:
    symbol: str
    quantity: float
    avg_cost: float          # cost basis per share (excludes fees)
    cost_basis: float        # quantity * avg_cost + accumulated fees on buys
    price: float | None
    market_value: float | None
    unrealized_pl: float | None
    unrealized_pl_pct: float | None
    weight_pct: float | None
    currency: str = "USD"    # quote currency from the routed provider


def ensure_account(name: str, currency: str = "USD", kind: str = "brokerage") -> int:
    with db.cursor() as cur:
        cur.execute("INSERT OR IGNORE INTO accounts(name,currency,kind) VALUES(?,?,?)",
                    (name, currency, kind))
        cur.execute("SELECT id FROM accounts WHERE name=?", (name,))
        return int(cur.fetchone()["id"])


def add_transaction(account: str, symbol: str, side: str, quantity: float,
                    price: float, fee: float = 0.0, executed_at: str | None = None,
                    currency: str = "USD", note: str | None = None) -> int:
    aid = ensure_account(account, currency)
    executed_at = executed_at or datetime.now(timezone.utc).isoformat()
    with db.cursor() as cur:
        cur.execute("""INSERT INTO transactions
            (account_id,symbol,side,quantity,price,fee,currency,executed_at,note)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (aid, symbol.upper(), side.upper(), quantity, price, fee, currency, executed_at, note))
        return int(cur.lastrowid)


def _holdings_raw(account: str | None) -> dict[str, dict]:
    """Aggregate by symbol using running-average cost basis."""
    with db.cursor() as cur:
        if account:
            cur.execute("""SELECT t.* FROM transactions t
                JOIN accounts a ON a.id=t.account_id
                WHERE a.name=? ORDER BY t.executed_at ASC""", (account,))
        else:
            cur.execute("SELECT * FROM transactions ORDER BY executed_at ASC")
        rows = cur.fetchall()

    hold: dict[str, dict] = {}
    for r in rows:
        sym, side, qty, px, fee = r["symbol"], r["side"], r["quantity"], r["price"], r["fee"]
        h = hold.setdefault(sym, {"quantity": 0.0, "cost_basis": 0.0, "realized": 0.0})
        if side == "BUY":
            h["cost_basis"] += qty * px + fee
            h["quantity"] += qty
        elif side == "SELL":
            avg = h["cost_basis"] / h["quantity"] if h["quantity"] else 0.0
            h["realized"] += (px - avg) * qty - fee
            h["cost_basis"] -= avg * qty
            h["quantity"] -= qty
        elif side == "DIV":
            h["realized"] += qty * px - fee
        elif side == "FEE":
            h["realized"] -= fee
    return {s: h for s, h in hold.items() if abs(h["quantity"]) > 1e-9}


async def holdings(account: str | None = None) -> list[Position]:
    raw = _holdings_raw(account)
    if not raw:
        return []
    quotes = await asyncio.gather(
        *(routed_quote(s) for s in raw), return_exceptions=True)

    # First pass: gather price + currency per symbol.
    tmp: list[tuple[str, dict, float | None, str]] = []
    # Weight totals are computed per-currency so IDR and USD do not blend.
    total_mv_by_ccy: dict[str, float] = {}
    for sym, q in zip(raw.keys(), quotes):
        if isinstance(q, Exception):
            price, ccy = None, "USD"
        else:
            price, ccy = q.price, (q.currency or "USD")
        mv = (price * raw[sym]["quantity"]) if price is not None else None
        if mv is not None:
            total_mv_by_ccy[ccy] = total_mv_by_ccy.get(ccy, 0.0) + mv
        tmp.append((sym, raw[sym], price, ccy))

    positions: list[Position] = []
    for sym, h, price, ccy in tmp:
        qty = h["quantity"]
        cost = h["cost_basis"]
        avg = cost / qty if qty else 0.0
        mv = (price * qty) if price is not None else None
        upl = (mv - cost) if mv is not None else None
        upl_pct = ((upl / cost) * 100) if (upl is not None and cost) else None
        denom = total_mv_by_ccy.get(ccy, 0.0)
        weight = ((mv / denom) * 100) if (mv is not None and denom) else None
        positions.append(Position(
            symbol=sym, quantity=qty, avg_cost=avg, cost_basis=cost,
            price=price, market_value=mv, unrealized_pl=upl,
            unrealized_pl_pct=upl_pct, weight_pct=weight, currency=ccy,
        ))
    positions.sort(key=lambda p: (p.market_value or 0), reverse=True)
    return positions


async def summary(account: str | None = None) -> dict:
    pos = await holdings(account)

    # Group totals by currency — never blend IDR + USD in one number.
    by_ccy: dict[str, dict[str, float]] = {}
    for p in pos:
        b = by_ccy.setdefault(p.currency, {"positions": 0, "market_value": 0.0,
                                           "cost_basis": 0.0})
        b["positions"] += 1
        b["market_value"] += (p.market_value or 0)
        b["cost_basis"] += p.cost_basis
    for b in by_ccy.values():
        b["unrealized_pl"] = b["market_value"] - b["cost_basis"]
        b["unrealized_pl_pct"] = (
            b["unrealized_pl"] / b["cost_basis"] * 100 if b["cost_basis"] else 0.0
        )

    with db.cursor() as cur:
        cur.execute("""SELECT COALESCE(SUM(
            CASE WHEN side='DIV' THEN quantity*price-fee
                 WHEN side='FEE' THEN -fee
                 ELSE 0 END),0) AS realized_income FROM transactions""")
        realized_income = float(cur.fetchone()["realized_income"])

    # Legacy top-level fields retained for back-compat callers; they
    # naively sum across currencies and are meaningful only when the
    # portfolio is single-currency. Prefer by_currency for mixed books.
    total_mv = sum((p.market_value or 0) for p in pos)
    total_cost = sum(p.cost_basis for p in pos)
    upl = total_mv - total_cost if pos else 0.0
    upl_pct = (upl / total_cost * 100) if total_cost else 0.0

    return {
        "account": account or "ALL",
        "positions": len(pos),
        "market_value": total_mv,
        "cost_basis": total_cost,
        "unrealized_pl": upl,
        "unrealized_pl_pct": upl_pct,
        "realized_income": realized_income,
        "by_currency": by_ccy,
        "holdings": [p.__dict__ for p in pos],
    }


async def allocation(account: str | None = None) -> dict:
    """Sector allocation via get_company lookup."""
    pos = await holdings(account)
    if not pos:
        return {"sectors": {}, "total_market_value": 0}
    companies = await asyncio.gather(
        *(routed_company(p.symbol) for p in pos), return_exceptions=True)
    buckets: dict[str, float] = {}
    total = sum((p.market_value or 0) for p in pos)
    for p, c in zip(pos, companies):
        sector = "Unknown" if isinstance(c, Exception) else (c.sector or "Unknown")
        buckets[sector] = buckets.get(sector, 0) + (p.market_value or 0)
    return {
        "total_market_value": total,
        "sectors": {k: {"value": v, "pct": (v/total*100 if total else 0)}
                    for k, v in sorted(buckets.items(), key=lambda x: -x[1])},
    }


async def risk(account: str | None = None) -> dict:
    """Concentration + top drawdown among holdings."""
    from .. import technical as ta
    pos = await holdings(account)
    if not pos:
        return {"positions": 0}
    total = sum((p.market_value or 0) for p in pos) or 1.0
    weights = [(p.symbol, (p.market_value or 0) / total) for p in pos]
    # Herfindahl concentration
    hhi = sum(w*w for _, w in weights) * 10000
    top5 = sum(w for _, w in sorted(weights, key=lambda x: -x[1])[:5]) * 100

    # Per-position 30d volatility + 6mo drawdown
    hist = await asyncio.gather(
        *(routed_history(p.symbol, "6mo", "1d") for p in pos),
        return_exceptions=True)
    per_sym = []
    for p, h in zip(pos, hist):
        if isinstance(h, Exception) or not h:
            per_sym.append({"symbol": p.symbol, "volatility_pct": None, "drawdown_pct": None})
            continue
        per_sym.append({
            "symbol": p.symbol,
            "weight_pct": (p.market_value or 0) / total * 100,
            "volatility_pct": ta.volatility(h, 30),
            "drawdown_pct": ta.drawdown(h),
        })
    return {
        "positions": len(pos),
        "concentration_hhi": hhi,        # 0=diversified, 10000=single holding
        "top5_weight_pct": top5,
        "per_position": per_sym,
    }
