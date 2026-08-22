"""Snapshot persistence and query building.

Every SQL fragment here is assembled from constants and from column names
this package owns (see fields.py). Caller-supplied values only ever travel as
bound parameters. Nothing from a filter is formatted into the statement.
"""
from __future__ import annotations

from typing import Any

from ..portfolio.db import connect
from .fields import Field, resolve, resolve_op

# Columns written by the snapshot job, in a fixed order.
COLUMNS = [
    "symbol", "snapshot_date", "market", "name", "sector", "industry",
    "currency", "price", "market_cap", "pe_ratio", "forward_pe", "peg_ratio",
    "price_to_book", "price_to_sales", "profit_margin", "operating_margin",
    "return_on_equity", "return_on_assets", "revenue_growth",
    "earnings_growth", "debt_to_equity", "current_ratio", "free_cashflow",
    "dividend_yield", "beta", "net_interest_margin",
    "non_performing_loan_ratio", "capital_adequacy_ratio",
    "loan_to_deposit_ratio", "casa_ratio", "loan_growth", "deposit_growth",
]


def upsert(row: dict[str, Any]) -> None:
    """Write one symbol's snapshot for one date, replacing any existing row."""
    values = [row.get(c) for c in COLUMNS]
    placeholders = ",".join("?" * len(COLUMNS))
    updates = ",".join(
        f"{c}=excluded.{c}" for c in COLUMNS
        if c not in ("symbol", "snapshot_date")
    )
    with connect() as conn:
        conn.execute(
            f"INSERT INTO screener_snapshot ({','.join(COLUMNS)})"
            f" VALUES ({placeholders})"
            f" ON CONFLICT(symbol, snapshot_date) DO UPDATE SET"
            f" {updates}, captured_at = datetime('now')",
            values,
        )


def latest_snapshot_date(market: str | None = None) -> str | None:
    q = "SELECT MAX(snapshot_date) d FROM screener_snapshot"
    args: tuple = ()
    if market and market.upper() != "ALL":
        q += " WHERE market=?"
        args = (market.upper(),)
    with connect() as conn:
        row = conn.execute(q, args).fetchone()
    return row["d"] if row else None


def _clause(f: Field, op: str, value: Any) -> tuple[str, list[Any]]:
    """One WHERE fragment. `f.column` is ours; `value` is always bound."""
    if op == "in":
        items = list(value) if isinstance(value, (list, tuple, set)) else [value]
        if not items:
            # An empty set matches nothing; say so in SQL rather than
            # producing "IN ()", which is a syntax error.
            return "0", []
        return f"{f.column} IN ({','.join('?' * len(items))})", list(items)
    sql_op = "=" if op == "=" else op
    return f"{f.column} {sql_op} ?", [value]


def query(filters: list[dict[str, Any]] | None = None, *,
          market: str = "ALL", order_by: str = "market_cap",
          desc: bool = True, limit: int = 50) -> dict[str, Any]:
    """Screen the most recent snapshot.

    `order_by` goes through the same allowlist as filters — an ORDER BY built
    from caller input is the other half of the injection surface, and it is
    easy to forget because it looks like a formatting concern.
    """
    order_field = resolve(order_by)
    snapshot_date = latest_snapshot_date(market)
    if snapshot_date is None:
        return {"snapshot_date": None, "count": 0, "rows": [],
                "reason": "no_snapshot_yet"}

    where = ["snapshot_date = ?"]
    args: list[Any] = [snapshot_date]

    if market and market.upper() != "ALL":
        where.append("market = ?")
        args.append(market.upper())

    for f in filters or []:
        field = resolve(f.get("field", ""))
        op = resolve_op(f.get("op", ""))
        clause, bound = _clause(field, op, f.get("value"))
        where.append(clause)
        args.extend(bound)
        # A filter on a metric implies the metric exists; otherwise NULL rows
        # would be silently excluded by SQL comparison anyway, but ordering
        # would still surface them.
        if field.numeric and op != "in":
            where.append(f"{field.column} IS NOT NULL")

    direction = "DESC" if desc else "ASC"
    sql = (
        f"SELECT {','.join(COLUMNS)} FROM screener_snapshot"
        f" WHERE {' AND '.join(where)}"
        # NULLs sort last regardless of direction: a screen for "highest ROE"
        # should not open with rows that have no ROE.
        f" ORDER BY ({order_field.column} IS NULL), {order_field.column} {direction}"
        f" LIMIT ?"
    )
    args.append(max(1, min(int(limit), 200)))

    with connect() as conn:
        rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
    return {"snapshot_date": snapshot_date, "count": len(rows), "rows": rows}
