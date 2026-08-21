"""Lot store — SQLite CRUD for ADR-0027."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import db

_SCHEMA = Path(__file__).parent / "lots_schema.sql"


def init() -> None:
    with db.connect() as conn:
        conn.executescript(_SCHEMA.read_text())


@dataclass
class Lot:
    symbol: str
    qty: float
    price: float
    acquired_at: str
    id: str = field(default_factory=lambda: f"l_{uuid.uuid4().hex[:16]}")
    account: str = "main"
    qty_remaining: float | None = None
    currency: str = "IDR"
    fee: float = 0.0
    tax: float = 0.0
    note: str | None = None

    def __post_init__(self) -> None:
        self.symbol = self.symbol.upper()
        if self.qty <= 0:
            raise ValueError("qty must be > 0")
        if self.qty_remaining is None:
            self.qty_remaining = self.qty


@dataclass
class Close:
    lot_id: str
    qty: float
    price: float
    closed_at: str
    id: int | None = None
    currency: str = "IDR"
    fee: float = 0.0
    tax: float = 0.0
    note: str | None = None


def record_buy(lot: Lot) -> str:
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO lots(id, account, symbol, qty, qty_remaining, "
            "price, currency, fee, tax, acquired_at, note) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (lot.id, lot.account, lot.symbol, lot.qty, lot.qty_remaining,
             lot.price, lot.currency, lot.fee, lot.tax, lot.acquired_at,
             lot.note),
        )
    return lot.id


def _open_lots_for(symbol: str, account: str) -> list[Lot]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM lots WHERE symbol=? AND account=? "
            "AND qty_remaining > 0 ORDER BY acquired_at ASC",
            (symbol.upper(), account),
        ).fetchall()
    return [
        Lot(
            id=r["id"], account=r["account"], symbol=r["symbol"],
            qty=r["qty"], qty_remaining=r["qty_remaining"],
            price=r["price"], currency=r["currency"], fee=r["fee"],
            tax=r["tax"], acquired_at=r["acquired_at"], note=r["note"],
        )
        for r in rows
    ]


def _rank_lots(lots: list[Lot], method: str) -> list[Lot]:
    m = method.upper()
    if m == "FIFO":
        return sorted(lots, key=lambda l: l.acquired_at)
    if m == "LIFO":
        return sorted(lots, key=lambda l: l.acquired_at, reverse=True)
    if m == "HIFO":
        return sorted(lots, key=lambda l: l.price, reverse=True)
    raise ValueError(f"unknown method: {method!r}")


def record_sell(*, symbol: str, qty: float, price: float,
                closed_at: str, method: str = "FIFO",
                currency: str = "IDR", fee: float = 0.0,
                tax: float = 0.0, account: str = "main",
                note: str | None = None) -> list[Close]:
    """Match `qty` against open lots using `method`; record closes.

    Returns the close records created. Raises ValueError if position is
    short (cannot close more than open).
    """
    if qty <= 0:
        raise ValueError("qty must be > 0")
    open_ = _open_lots_for(symbol, account)
    ranked = _rank_lots(open_, method)
    total_open = sum(l.qty_remaining for l in ranked)
    if qty > total_open + 1e-9:
        raise ValueError(
            f"insufficient qty for {symbol}: want {qty}, open {total_open}"
        )
    remaining = qty
    closes: list[Close] = []
    with db.connect() as conn:
        for lot in ranked:
            if remaining <= 0:
                break
            take = min(lot.qty_remaining, remaining)
            cur = conn.execute(
                "INSERT INTO lot_closes(lot_id, qty, price, currency, "
                "fee, tax, closed_at, note) VALUES(?,?,?,?,?,?,?,?)",
                (lot.id, take, price, currency, fee, tax, closed_at, note),
            )
            close = Close(id=cur.lastrowid, lot_id=lot.id, qty=take,
                          price=price, closed_at=closed_at,
                          currency=currency, fee=fee, tax=tax, note=note)
            closes.append(close)
            new_remaining = lot.qty_remaining - take
            conn.execute("UPDATE lots SET qty_remaining=? WHERE id=?",
                         (new_remaining, lot.id))
            remaining -= take
    return closes


def list_lots(symbol: str | None = None, *, open_only: bool = True,
              account: str = "main") -> list[dict[str, Any]]:
    q = "SELECT * FROM lots WHERE account=?"
    args: list[Any] = [account]
    if symbol:
        q += " AND symbol=?"
        args.append(symbol.upper())
    if open_only:
        q += " AND qty_remaining > 0"
    q += " ORDER BY acquired_at ASC"
    with db.connect() as conn:
        rows = conn.execute(q, tuple(args)).fetchall()
    return [dict(r) for r in rows]


def list_closes(symbol: str | None = None,
                account: str = "main") -> list[dict[str, Any]]:
    q = ("SELECT c.* FROM lot_closes c "
         "JOIN lots l ON l.id = c.lot_id WHERE l.account=?")
    args: list[Any] = [account]
    if symbol:
        q += " AND l.symbol=?"
        args.append(symbol.upper())
    q += " ORDER BY c.closed_at ASC"
    with db.connect() as conn:
        rows = conn.execute(q, tuple(args)).fetchall()
    return [dict(r) for r in rows]


def positions(account: str = "main") -> dict[str, dict[str, float]]:
    """Aggregate open lots per symbol → qty + cost_basis + wavg_price."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT symbol, SUM(qty_remaining) AS qty, "
            "SUM(qty_remaining * price) AS cost_no_fee, "
            "SUM(fee) AS fee "
            "FROM lots WHERE account=? AND qty_remaining > 0 "
            "GROUP BY symbol",
            (account,),
        ).fetchall()
    out: dict[str, dict[str, float]] = {}
    for r in rows:
        q = float(r["qty"] or 0.0)
        cost = float(r["cost_no_fee"] or 0.0) + float(r["fee"] or 0.0)
        out[r["symbol"]] = {
            "qty": q,
            "cost_basis": cost,
            "avg_price": (cost / q) if q > 0 else 0.0,
        }
    return out
