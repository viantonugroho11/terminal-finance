"""IDX flow deep-dive parsers — ADR-0026. Uses stubbed _get_json."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from finance_mcp.providers.idx import IdxProvider


@pytest.fixture
def prov() -> IdxProvider:
    return IdxProvider()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if asyncio.get_event_loop().is_running() else asyncio.run(coro)


def test_insider_trades_parses_rows(prov: IdxProvider,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    stub = AsyncMock(return_value={"data": [
        {"Date": "2026-08-01", "Name": "John Director", "Role": "Director",
         "Side": "BUY", "Quantity": 10000, "Price": 9500.0,
         "TotalValue": 95_000_000.0, "Url": "https://idx.co.id/x"},
        {"Date": "2026-08-05", "Name": "Bad Row"},  # missing side → best-effort
    ]})
    monkeypatch.setattr(prov, "_get_json", stub)
    out = asyncio.run(prov.insider_trades("BBCA", days=30))
    assert out.symbol == "BBCA.JK"
    assert out.days == 30
    assert len(out.trades) == 2
    assert out.trades[0].side == "BUY"
    assert out.trades[0].qty == 10000


def test_major_holder_changes_computes_delta(prov: IdxProvider,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    stub = AsyncMock(return_value={"data": [
        {"Date": "2026-08-10", "Holder": "Fund X",
         "PctBefore": 5.0, "PctAfter": 6.5},
        {"Date": "2026-08-11", "Holder": "Fund Y",
         "PctBefore": 7.0, "PctAfter": 6.5, "Change": -0.5},
    ]})
    monkeypatch.setattr(prov, "_get_json", stub)
    out = asyncio.run(prov.major_holder_changes("BBCA"))
    assert len(out.changes) == 2
    assert out.changes[0].change_pct == pytest.approx(1.5)
    assert out.changes[1].change_pct == pytest.approx(-0.5)


def test_broker_flow_agg_ranks_buyers_and_sellers(
    prov: IdxProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    from finance_mcp.models import BrokerActivity, BrokerActivityRow
    fake_day = BrokerActivity(
        symbol="BBCA.JK", date="2026-08-13",
        rows=[
            BrokerActivityRow(broker_code="AA", broker_name="Alpha",
                              buy_lot=None, sell_lot=None,
                              buy_value=1_000_000_000, sell_value=200_000_000,
                              net_value=800_000_000),
            BrokerActivityRow(broker_code="BB", broker_name="Beta",
                              buy_lot=None, sell_lot=None,
                              buy_value=100_000_000, sell_value=900_000_000,
                              net_value=-800_000_000),
            BrokerActivityRow(broker_code="CC", broker_name="Gamma",
                              buy_lot=None, sell_lot=None,
                              buy_value=500_000_000, sell_value=500_000_000,
                              net_value=0),
        ],
    )
    monkeypatch.setattr(prov, "broker_activity", AsyncMock(return_value=fake_day))
    out = asyncio.run(prov.broker_flow_agg("BBCA", days=5))
    assert out.symbol == "BBCA.JK"
    assert out.top_net_buyers[0].broker_code == "AA"
    assert out.top_net_buyers[0].net_value == 800_000_000
    assert out.top_net_sellers[0].broker_code == "BB"
    assert out.top_net_sellers[0].net_value == -800_000_000
