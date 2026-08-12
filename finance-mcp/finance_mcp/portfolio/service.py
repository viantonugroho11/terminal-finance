"""Portfolio calc — deterministic. Never ask LLM to sum holdings."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from . import db
from ..providers.yahoo import YahooProvider

_market = YahooProvider()


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
    quotes = await asyncio.gather(*(_market.quote(s) for s in raw), return_exceptions=True)
    positions: list[Position] = []
    total_mv = 0.0
    tmp: list[tuple[str, dict, float | None]] = []
    for sym, q in zip(raw.keys(), quotes):
        price = None if isinstance(q, Exception) else q.price
        mv = (price * raw[sym]["quantity"]) if price is not None else None
        if mv is not None:
            total_mv += mv
        tmp.append((sym, raw[sym], price))

    for sym, h, price in tmp:
        qty = h["quantity"]
        cost = h["cost_basis"]
        avg = cost / qty if qty else 0.0
        mv = (price * qty) if price is not None else None
        upl = (mv - cost) if mv is not None else None
        upl_pct = ((upl / cost) * 100) if (upl is not None and cost) else None
        weight = ((mv / total_mv) * 100) if (mv is not None and total_mv) else None
        positions.append(Position(
            symbol=sym, quantity=qty, avg_cost=avg, cost_basis=cost,
            price=price, market_value=mv, unrealized_pl=upl,
            unrealized_pl_pct=upl_pct, weight_pct=weight,
        ))
    positions.sort(key=lambda p: (p.market_value or 0), reverse=True)
    return positions


async def summary(account: str | None = None) -> dict:
    pos = await holdings(account)
    total_mv = sum((p.market_value or 0) for p in pos)
    total_cost = sum(p.cost_basis for p in pos)
    upl = total_mv - total_cost if pos else 0.0
    upl_pct = (upl / total_cost * 100) if total_cost else 0.0

    with db.cursor() as cur:
        cur.execute("""SELECT COALESCE(SUM(
            CASE WHEN side='DIV' THEN quantity*price-fee
                 WHEN side='FEE' THEN -fee
                 ELSE 0 END),0) AS realized_income FROM transactions""")
        realized_income = float(cur.fetchone()["realized_income"])

    return {
        "account": account or "ALL",
        "positions": len(pos),
        "market_value": total_mv,
        "cost_basis": total_cost,
        "unrealized_pl": upl,
        "unrealized_pl_pct": upl_pct,
        "realized_income": realized_income,
        "holdings": [p.__dict__ for p in pos],
    }


async def allocation(account: str | None = None) -> dict:
    """Sector allocation via get_company lookup."""
    pos = await holdings(account)
    if not pos:
        return {"sectors": {}, "total_market_value": 0}
    companies = await asyncio.gather(
        *(_market.company(p.symbol) for p in pos), return_exceptions=True)
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
        *(_market.history(p.symbol, "6mo", "1d") for p in pos), return_exceptions=True)
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
