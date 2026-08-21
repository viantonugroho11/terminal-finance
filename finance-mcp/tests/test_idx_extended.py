"""IdxProvider extended capabilities — mocked HTTP."""
import asyncio

import httpx
import pytest
from finance_mcp.providers.idx import IdxProvider


def _client(handler):
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://www.idx.co.id",
    )


def _run(coro): return asyncio.run(coro)


def test_foreign_flow_parses():
    def handler(req):
        assert "GetForeignFlow" in req.url.path
        return httpx.Response(200, json={"data": [
            {"Date": "2025-08-13", "ForeignBuy": 1e9, "ForeignSell": 8e8},
            {"Date": "2025-08-12", "ForeignBuy": 5e8, "ForeignSell": 6e8},
        ]})
    p = IdxProvider(http=_client(handler))
    r = _run(p.foreign_flow("BBCA"))
    assert r.symbol == "BBCA.JK"
    assert len(r.days) == 2
    assert r.days[0].net_value == 2e8
    assert r.days[1].net_value == -1e8


def test_search_parses():
    def handler(req):
        return httpx.Response(200, json={"data": [
            {"KodeEmiten": "BBCA", "NamaEmiten": "Bank Central Asia Tbk",
             "Sektor": "Financials"},
            {"KodeEmiten": "BBRI", "NamaEmiten": "Bank Rakyat Indonesia Tbk",
             "Sektor": "Financials"},
        ]})
    p = IdxProvider(http=_client(handler))
    out = _run(p.search("bank", limit=5))
    assert len(out) == 2
    assert out[0].symbol == "BBCA.JK"
    assert out[0].name.startswith("Bank Central")
    assert out[0].sector == "Financials"


def test_search_empty_query_returns_empty():
    p = IdxProvider(http=_client(lambda r: httpx.Response(200, json={})))
    assert _run(p.search("", limit=5)) == []


def test_broker_activity_parses_and_computes_net():
    def handler(req):
        return httpx.Response(200, json={"date": "2025-08-13", "data": [
            {"BrokerCode": "YP", "BrokerName": "MockSec",
             "BuyLot": 1000, "SellLot": 800,
             "BuyValue": 1e9, "SellValue": 8e8},
            {"BrokerCode": "CC", "BrokerName": "MockBroker",
             "BuyLot": 500, "SellLot": 700,
             "BuyValue": 5e8, "SellValue": 7e8, "NetValue": -2e8},
        ]})
    p = IdxProvider(http=_client(handler))
    r = _run(p.broker_activity("BBCA"))
    assert r.symbol == "BBCA.JK"
    assert len(r.rows) == 2
    assert r.rows[0].net_value == 2e8  # computed
    assert r.rows[1].net_value == -2e8  # provided


def test_order_book_parses_bids_asks():
    def handler(req):
        return httpx.Response(200, json={
            "timestamp": "2025-08-13T04:00:00Z",
            "bids": [{"Price": 9500, "Volume": 1000, "Orders": 5},
                     {"Price": 9490, "Volume": 2000}],
            "asks": [{"Price": 9510, "Volume": 1500},
                     {"Price": 9520, "Volume": 3000}],
        })
    p = IdxProvider(http=_client(handler))
    ob = _run(p.order_book("BBCA"))
    assert ob.symbol == "BBCA.JK"
    assert len(ob.bids) == 2
    assert ob.bids[0].price == 9500 and ob.bids[0].volume == 1000
    assert ob.bids[0].orders == 5
    assert ob.asks[0].price == 9510


def test_ipo_calendar_parses():
    def handler(req):
        return httpx.Response(200, json={"data": [
            {"Code": "NEWA", "Name": "New Company Tbk",
             "ListingDate": "2025-08-20", "OfferPrice": 100,
             "SharesOffered": 1_000_000, "Sector": "Technology"},
        ]})
    p = IdxProvider(http=_client(handler))
    cal = _run(p.ipo_calendar())
    assert len(cal.events) == 1
    assert cal.events[0].symbol == "NEWA.JK"
    assert cal.events[0].offer_price == 100.0
    assert cal.events[0].shares_offered == 1_000_000


def test_trading_calendar_parses():
    def handler(req):
        return httpx.Response(200, json={"data": [
            {"Date": "2025-01-01", "IsTradingDay": False,
             "HolidayName": "New Year"},
            {"Date": "2025-01-02", "IsTradingDay": True},
        ]})
    p = IdxProvider(http=_client(handler))
    tc = _run(p.trading_calendar(2025))
    assert tc.year == 2025
    assert len(tc.days) == 2
    assert tc.days[0].is_trading_day is False
    assert tc.days[0].holiday_name == "New Year"


def test_disclosures_parses():
    def handler(req):
        return httpx.Response(200, json={"data": [
            {"Date": "2025-08-10", "Title": "Q2 Financial Report",
             "Category": "Financial Report",
             "Url": "https://idx.co.id/x"},
        ]})
    p = IdxProvider(http=_client(handler))
    d = _run(p.disclosures("BBCA", limit=5))
    assert d.symbol == "BBCA.JK"
    assert d.items[0].title == "Q2 Financial Report"


def test_board_parses_commissioners_and_directors():
    def handler(req):
        return httpx.Response(200, json={
            "Commissioner": [{"Name": "Ali", "Position": "Preskom", "Since": "2020"}],
            "Director":     [{"Name": "Budi", "Position": "Presdir", "Since": "2021"}],
        })
    p = IdxProvider(http=_client(handler))
    b = _run(p.board("BBCA"))
    assert b.commissioners[0].name == "Ali"
    assert b.directors[0].position == "Presdir"


def test_shareholders_parses():
    def handler(req):
        return httpx.Response(200, json={"data": [
            {"Name": "PT Dwimuria", "Type": "institution",
             "Shares": 130_000_000_000, "Percentage": 54.94},
            {"Name": "Public", "Type": "institution",
             "Shares": 60_000_000_000, "Percentage": 25.06},
        ]})
    p = IdxProvider(http=_client(handler))
    s = _run(p.shareholders("BBCA"))
    assert s.symbol == "BBCA.JK"
    assert len(s.holders) == 2
    assert s.holders[0].pct == 54.94


def test_subsidiaries_parses():
    def handler(req):
        return httpx.Response(200, json={"data": [
            {"Name": "BCA Finance", "Ownership": 100.0,
             "Business": "Multi-finance"},
            {"Name": "BCA Sekuritas", "Ownership": 99.9,
             "Business": "Securities"},
        ]})
    p = IdxProvider(http=_client(handler))
    subs = _run(p.subsidiaries("BBCA"))
    assert len(subs.subsidiaries) == 2
    assert subs.subsidiaries[0].ownership_pct == 100.0


def test_idx_market_overview_parses_indices_and_sectors():
    def handler(req):
        if "GetIndexData" in req.url.path:
            return httpx.Response(200, json={"data": [
                {"Code": "COMPOSITE", "Value": 7500, "Previous": 7475,
                 "Volume": 15_000_000_000, "ValueTraded": 1.2e13},
                {"Code": "LQ45", "Value": 1000, "Previous": 997,
                 "Volume": 5_000_000_000, "ValueTraded": 6e12},
            ]})
        return httpx.Response(200, json={"data": [
            {"Code": "A", "Name": "Financials", "ChangePct": 0.85,
             "ValueTraded": 4e12},
            {"Code": "G", "Name": "Technology", "ChangePct": -0.40,
             "ValueTraded": 8e11},
        ]})
    p = IdxProvider(http=_client(handler))
    ov = _run(p.idx_market_overview())
    assert len(ov.indices) == 2
    assert ov.indices[0].code == "COMPOSITE"
    assert ov.indices[0].change == 25.0
    assert len(ov.sectors) == 2
    assert ov.sectors[0].sector_name == "Financials"


def test_idx_market_movers_fetches_three_lists():
    calls: list[str] = []
    def handler(req):
        kind = req.url.params.get("type", "")
        calls.append(kind)
        return httpx.Response(200, json={"data": [
            {"Code": f"{kind[:4].upper():<4}", "Name": f"{kind} sample",
             "Close": 1000, "Previous": 950, "Volume": 1_000_000},
        ]})
    p = IdxProvider(http=_client(handler))
    m = _run(p.idx_market_movers())
    assert set(calls) == {"gainer", "loser", "active"}
    assert len(m.top_gainers) == 1
    assert m.top_gainers[0].symbol.endswith(".JK")
    assert m.top_gainers[0].change_percent == pytest.approx((50 / 950) * 100)


def test_extended_capabilities_advertised():
    p = IdxProvider(http=_client(lambda r: httpx.Response(200, json={})))
    for c in ("foreign_flow", "search", "broker_activity", "order_book",
              "ipo_calendar", "trading_calendar", "disclosures",
              "board", "shareholders", "subsidiaries",
              "idx_market_overview", "idx_market_movers"):
        assert c in p.capabilities
