"""Persistence for daily broker-activity snapshots."""
from __future__ import annotations

from typing import Any

from ..models import BrokerAggRow, BrokerFlowAggregate
from ..portfolio.db import connect


def upsert_day(symbol: str, date: str, rows: list[Any]) -> int:
    """Record one trading day for one symbol. Returns rows written.

    Idempotent by primary key: re-running a snapshot for a date that is
    already stored replaces it instead of double-counting.
    """
    if not date or not rows:
        return 0
    payload = [
        (symbol.upper(), date, r.broker_code, r.broker_name,
         float(r.buy_value or 0.0), float(r.sell_value or 0.0),
         float(r.net_value or 0.0))
        for r in rows
    ]
    with connect() as conn:
        conn.executemany(
            "INSERT INTO broker_daily"
            " (symbol, date, broker_code, broker_name, buy_value, sell_value,"
            "  net_value)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(symbol, date, broker_code) DO UPDATE SET"
            "   broker_name = excluded.broker_name,"
            "   buy_value   = excluded.buy_value,"
            "   sell_value  = excluded.sell_value,"
            "   net_value   = excluded.net_value,"
            "   captured_at = datetime('now')",
            payload,
        )
    return len(payload)


def stored_dates(symbol: str, days: int) -> list[str]:
    """The most recent `days` trading dates held for `symbol`, newest first."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT date FROM broker_daily WHERE symbol=?"
            " ORDER BY date DESC LIMIT ?",
            (symbol.upper(), int(days)),
        ).fetchall()
    return [r["date"] for r in rows]


def aggregate(symbol: str, days: int) -> BrokerFlowAggregate | None:
    """Sum stored days into a ranked buyer/seller view.

    Returns None when nothing is stored yet, so the caller can fall back to a
    live single-day fetch rather than reporting an empty result.
    """
    sym = symbol.upper()
    dates = stored_dates(sym, days)
    if not dates:
        return None
    placeholders = ",".join("?" * len(dates))
    with connect() as conn:
        rows = conn.execute(
            "SELECT broker_code,"
            "       MAX(broker_name)      AS broker_name,"
            "       SUM(buy_value)        AS buy_value,"
            "       SUM(sell_value)       AS sell_value,"
            "       SUM(net_value)        AS net_value,"
            "       COUNT(DISTINCT date)  AS days_active"
            "  FROM broker_daily"
            " WHERE symbol=? AND date IN (" + placeholders + ")"
            " GROUP BY broker_code",
            (sym, *dates),
        ).fetchall()

    aggregated = [
        BrokerAggRow(
            broker_code=r["broker_code"], broker_name=r["broker_name"],
            net_value=r["net_value"], buy_value=r["buy_value"],
            sell_value=r["sell_value"], days_active=r["days_active"],
        )
        for r in rows
    ]
    aggregated.sort(key=lambda r: r.net_value, reverse=True)
    return BrokerFlowAggregate(
        symbol=f"{sym.replace('.JK', '')}.JK",
        days=len(dates),
        top_net_buyers=aggregated[:10],
        top_net_sellers=sorted(aggregated, key=lambda r: r.net_value)[:10],
    )
