"""Snapshot and aggregate broker flow across trading days.

Providers stay stateless adapters (ADR-0002), so the storage lives here rather
than on IdxProvider: the provider answers for one session, this module keeps
the history.
"""
from __future__ import annotations

from typing import Any

from ..models import BrokerFlowAggregate
from ..retry import with_retry
from . import store


async def _fetch_day(symbol: str) -> Any:
    """Latest session's broker activity, through the normal router path."""
    from ..registry import router

    async def _call(p, s):
        return await with_retry(lambda: p.broker_activity(s),
                                provider=p.name, symbol=s)

    value, _, _ = await router.call(
        "broker_activity", symbol=symbol, fetch=lambda p: _call(p, symbol),
    )
    return value


def _rows_and_date(payload: Any) -> tuple[str | None, list[Any]]:
    """Accept either a BrokerActivity dataclass or its dict form."""
    if payload is None:
        return None, []
    if isinstance(payload, dict):
        rows = payload.get("rows") or []
        # Rows may already be dicts; give them attribute access.
        return payload.get("date"), [_Row(r) if isinstance(r, dict) else r
                                     for r in rows]
    return getattr(payload, "date", None), list(getattr(payload, "rows", []))


class _Row:
    """Attribute view over a dict row, so store.upsert_day sees one shape."""

    __slots__ = ("broker_code", "broker_name", "buy_value", "sell_value",
                 "net_value")

    def __init__(self, d: dict):
        self.broker_code = d.get("broker_code")
        self.broker_name = d.get("broker_name")
        self.buy_value = d.get("buy_value")
        self.sell_value = d.get("sell_value")
        self.net_value = d.get("net_value")


async def snapshot_symbol(symbol: str) -> dict:
    """Capture today's broker activity for one symbol."""
    try:
        payload = await _fetch_day(symbol)
    except Exception as e:
        return {"symbol": symbol.upper(), "stored": 0,
                "error": f"{type(e).__name__}: {e}"}
    date, rows = _rows_and_date(payload)
    if not date or not rows:
        return {"symbol": symbol.upper(), "stored": 0, "reason": "no_data"}
    written = store.upsert_day(symbol, date, rows)
    return {"symbol": symbol.upper(), "date": date, "stored": written}


def tracked_symbols() -> list[str]:
    """Symbols worth spending a daily fetch on.

    Watchlist entries and active watches — what the user actually follows.
    Snapshotting the whole exchange daily would be a lot of requests for data
    nobody asked about.
    """
    from ..portfolio.db import connect
    with connect() as conn:
        rows = conn.execute(
            "SELECT symbol FROM watchlist_items"
            " UNION"
            " SELECT symbol FROM watches WHERE disabled=0"
        ).fetchall()
    return sorted({r["symbol"].upper() for r in rows if r["symbol"]})


async def snapshot_once(symbols: list[str] | None = None) -> dict:
    """Snapshot every tracked symbol. Intended for a daily post-close cron."""
    targets = symbols if symbols is not None else tracked_symbols()
    results = [await snapshot_symbol(s) for s in targets]
    return {
        "symbols": len(targets),
        "stored": sum(r.get("stored", 0) for r in results),
        "results": results,
    }


async def aggregate(symbol: str, days: int = 5) -> BrokerFlowAggregate:
    """Multi-day aggregate from stored snapshots.

    Falls back to a live single-day fetch while no history exists yet, so the
    tool keeps working on the day this ships rather than returning nothing
    until the first cron run.
    """
    stored = store.aggregate(symbol, days)
    if stored is not None:
        return stored

    payload = await _fetch_day(symbol)
    date, rows = _rows_and_date(payload)
    if date and rows:
        store.upsert_day(symbol, date, rows)
        again = store.aggregate(symbol, days)
        if again is not None:
            return again
    sym = symbol.upper().replace(".JK", "")
    return BrokerFlowAggregate(symbol=f"{sym}.JK", days=0)
