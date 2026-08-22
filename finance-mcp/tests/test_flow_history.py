"""Multi-day broker flow, built from local daily snapshots.

ADR-0026 shipped `broker_flow_agg(symbol, days=5)` against an upstream
endpoint that only answers for the latest session, so `days` never meant
anything. These cover the replacement: snapshot per trading day, aggregate
across the days actually held.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass

import pytest

os.environ.setdefault(
    "FINANCE_DB", tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
)

from finance_mcp.flow import db as fldb  # noqa: E402
from finance_mcp.flow import service, store  # noqa: E402
from finance_mcp.portfolio import db as pdb  # noqa: E402
from finance_mcp.watch import db as wdb  # noqa: E402


@dataclass
class Row:
    broker_code: str
    broker_name: str | None
    buy_value: float
    sell_value: float
    net_value: float


def _day(code_to_net: dict[str, float]) -> list[Row]:
    return [
        Row(broker_code=c, broker_name=f"Broker {c}",
            buy_value=max(n, 0.0), sell_value=abs(min(n, 0.0)), net_value=n)
        for c, n in code_to_net.items()
    ]


@pytest.fixture
def db(monkeypatch, tmp_path):
    monkeypatch.setenv("FINANCE_DB", str(tmp_path / "flow.db"))
    pdb.init(); wdb.init(); fldb.init()


def test_aggregate_sums_across_days(db):
    store.upsert_day("BBCA", "2026-08-17", _day({"AA": 100.0, "BB": -50.0}))
    store.upsert_day("BBCA", "2026-08-18", _day({"AA": 200.0, "BB": -20.0}))
    store.upsert_day("BBCA", "2026-08-19", _day({"AA": 300.0, "CC": -10.0}))

    agg = store.aggregate("BBCA", days=5)

    assert agg.days == 3
    top = {r.broker_code: r for r in agg.top_net_buyers}
    assert top["AA"].net_value == 600.0        # 100 + 200 + 300
    assert top["AA"].days_active == 3
    assert top["BB"].days_active == 2
    assert agg.top_net_sellers[0].broker_code == "BB"   # -70, most negative


def test_days_window_limits_to_most_recent(db):
    for i, date in enumerate(["2026-08-17", "2026-08-18", "2026-08-19"]):
        store.upsert_day("BBCA", date, _day({"AA": 10.0 * (i + 1)}))

    agg = store.aggregate("BBCA", days=2)

    assert agg.days == 2
    # Only the two newest days: 20 + 30, not the 10 from the oldest.
    assert agg.top_net_buyers[0].net_value == 50.0


def test_resnapshotting_a_day_replaces_rather_than_doubles(db):
    store.upsert_day("BBCA", "2026-08-19", _day({"AA": 100.0}))
    store.upsert_day("BBCA", "2026-08-19", _day({"AA": 100.0}))

    agg = store.aggregate("BBCA", days=5)

    assert agg.days == 1
    assert agg.top_net_buyers[0].net_value == 100.0
    assert agg.top_net_buyers[0].days_active == 1


def test_aggregate_returns_none_when_nothing_stored(db):
    assert store.aggregate("BBCA", days=5) is None


def test_service_falls_back_to_a_live_fetch_on_an_empty_history(db, monkeypatch):
    """The tool must still answer on the day this ships, before any cron run."""
    async def fake_fetch(symbol):
        return {"symbol": "BBCA.JK", "date": "2026-08-21",
                "rows": [{"broker_code": "AA", "broker_name": "Alpha",
                          "buy_value": 500.0, "sell_value": 100.0,
                          "net_value": 400.0}]}

    monkeypatch.setattr(service, "_fetch_day", fake_fetch)
    agg = asyncio.run(service.aggregate("BBCA", days=5))

    assert agg.days == 1
    assert agg.top_net_buyers[0].net_value == 400.0
    # The fetched day is kept, so the history starts filling from first use.
    assert store.stored_dates("BBCA", 5) == ["2026-08-21"]


def test_service_prefers_stored_history_over_fetching(db, monkeypatch):
    store.upsert_day("BBCA", "2026-08-20", _day({"AA": 700.0}))

    async def explode(symbol):
        raise AssertionError("must not fetch when history exists")

    monkeypatch.setattr(service, "_fetch_day", explode)
    agg = asyncio.run(service.aggregate("BBCA", days=5))
    assert agg.top_net_buyers[0].net_value == 700.0


def test_tracked_symbols_come_from_watchlists_and_active_watches(db):
    from finance_mcp.portfolio.db import connect
    with connect() as conn:
        conn.execute("INSERT INTO watchlists (id, name) VALUES (1, 'Core')")
        conn.execute(
            "INSERT INTO watchlist_items (watchlist_id, symbol)"
            " VALUES (1, 'BBCA')"
        )
        conn.execute(
            "INSERT INTO watches (id, symbol, metric, op, threshold, disabled)"
            " VALUES ('w1', 'BBRI', 'price_change_pct_1d', '>', 1.0, 0)"
        )
        conn.execute(
            "INSERT INTO watches (id, symbol, metric, op, threshold, disabled)"
            " VALUES ('w2', 'TLKM', 'price_change_pct_1d', '>', 1.0, 1)"
        )

    # Disabled watches are not worth a daily request.
    assert service.tracked_symbols() == ["BBCA", "BBRI"]


def test_snapshot_reports_errors_without_raising(db, monkeypatch):
    async def boom(symbol):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(service, "_fetch_day", boom)
    out = asyncio.run(service.snapshot_symbol("BBCA"))

    assert out["stored"] == 0
    assert "upstream down" in out["error"]
