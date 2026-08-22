"""Building the snapshot, and screening it.

The snapshot exists because screening live would mean one upstream call per
ticker per question — 435 for a single IDX screen. Once a day, in the
background, is the right shape for data that moves daily.
"""
from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from typing import Any

from ..retry import with_retry
from . import store

_TICKERS = Path(__file__).parent.parent / "data" / "idx_tickers.txt"

# Concurrency against a single upstream. Yahoo starts returning empties above
# roughly one request per second (docs/PROVIDERS.md), so this stays modest.
_WORKERS = 4


def idx_universe() -> list[str]:
    if not _TICKERS.exists():
        return []
    return [
        line.strip().upper()
        for line in _TICKERS.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_dict(payload: Any) -> dict:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return payload
    return {k: getattr(payload, k) for k in dir(payload)
            if not k.startswith("_") and not callable(getattr(payload, k))}


async def _gather(symbol: str) -> dict[str, Any]:
    """One symbol's row, from the same tools a user would call by hand."""
    from ..registry import router

    async def _call(capability: str, method: str):
        async def _fetch(p):
            return await with_retry(lambda: getattr(p, method)(symbol),
                                    provider=p.name, symbol=symbol)
        value, _, _ = await router.call(capability, symbol=symbol, fetch=_fetch)
        return _as_dict(value)

    fundamentals = await _call("financials", "financials")
    company = await _call("company", "company")
    quote = await _call("quote", "quote")

    row: dict[str, Any] = {
        "symbol": symbol.upper(),
        "snapshot_date": date.today().isoformat(),
        "market": "IDX",
        "name": company.get("name"),
        "sector": company.get("sector"),
        "industry": company.get("industry"),
        "currency": quote.get("currency"),
        "price": _num(quote.get("price")),
        "market_cap": _num(company.get("market_cap")),
    }
    for column in store.COLUMNS:
        if column in row:
            continue
        row[column] = _num(fundamentals.get(column))
    return row


async def snapshot_once(symbols: list[str] | None = None,
                        *, limit: int | None = None) -> dict:
    """Refresh the snapshot. Intended for a nightly cron.

    Failures are counted, not raised: one delisted ticker must not abort a
    435-symbol run.
    """
    targets = symbols if symbols is not None else idx_universe()
    if limit is not None:
        targets = targets[:limit]

    written, failed = 0, 0
    semaphore = asyncio.Semaphore(_WORKERS)

    async def _one(sym: str) -> None:
        nonlocal written, failed
        async with semaphore:
            try:
                store.upsert(await _gather(sym))
                written += 1
            except Exception:
                failed += 1

    await asyncio.gather(*(_one(s) for s in targets))
    return {"requested": len(targets), "written": written, "failed": failed,
            "snapshot_date": date.today().isoformat()}


def screen(filters: list[dict[str, Any]] | None = None, *,
           market: str = "ALL", order_by: str = "market_cap",
           desc: bool = True, limit: int = 50) -> dict:
    return store.query(filters, market=market, order_by=order_by,
                       desc=desc, limit=limit)
