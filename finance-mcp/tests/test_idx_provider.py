"""IdxProvider unit tests — mocked HTTP, no network."""
import asyncio

import httpx
import pytest
from finance_mcp.errors import ErrorCode, FinanceError
from finance_mcp.providers.idx import IdxProvider


def _client(handler):
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, base_url="https://www.idx.co.id")


def _run(coro): return asyncio.run(coro)


def test_bare_strips_jk_and_rejects_bad():
    from finance_mcp.providers.idx import _bare
    assert _bare("BBCA.JK") == "BBCA"
    assert _bare("bbca") == "BBCA"
    with pytest.raises(FinanceError) as ei:
        _bare("BB")
    assert ei.value.code == ErrorCode.INVALID_SYMBOL


def test_quote_parses_summary():
    def handler(req: httpx.Request) -> httpx.Response:
        assert "GetStockSummary" in req.url.path
        return httpx.Response(200, json={
            "data": [{"Close": 9500, "Previous": 9400, "Volume": 12_345_000}]
        })
    p = IdxProvider(http=_client(handler))
    q = _run(p.quote("BBCA"))
    assert q.symbol == "BBCA.JK"
    assert q.price == 9500.0
    assert q.change == 100.0
    assert q.currency == "IDR"
    assert q.volume == 12_345_000


def test_quote_missing_rows_raises_not_found():
    def handler(req): return httpx.Response(200, json={"data": []})
    p = IdxProvider(http=_client(handler))
    with pytest.raises(FinanceError) as ei:
        _run(p.quote("BBCA"))
    assert ei.value.code == ErrorCode.SYMBOL_NOT_FOUND


def test_cloudflare_403_maps_to_provider_unavailable():
    def handler(req): return httpx.Response(403, text="challenge")
    p = IdxProvider(http=_client(handler))
    with pytest.raises(FinanceError) as ei:
        _run(p.quote("BBCA"))
    assert ei.value.code == ErrorCode.PROVIDER_UNAVAILABLE


def test_company_profile_parses():
    def handler(req):
        return httpx.Response(200, json={"Profiles": [{
            "Name": "Bank Central Asia Tbk",
            "Sector": "Financials",
            "Industry": "Banks",
            "Website": "https://bca.co.id",
            "Employees": "27000",
            "BusinessDescription": "Bank swasta terbesar.",
            "MarketCap": 1200000000000000,
        }]})
    p = IdxProvider(http=_client(handler))
    c = _run(p.company("BBCA"))
    assert c.symbol == "BBCA.JK"
    assert c.name.startswith("Bank Central Asia")
    assert c.sector == "Financials"
    assert c.employees == 27000
    assert c.market_cap == 1_200_000_000_000_000.0
    assert c.country == "ID"


def test_financials_maps_banking_metrics():
    def handler(req):
        return httpx.Response(200, json={"data": [{
            "PER": 22.1, "PBV": 5.4, "ROE": 21.3, "ROA": 3.1,
            "NIM": 5.7, "NPL": 2.1, "CAR": 25.0, "LDR": 78.4, "CASA": 82.0,
        }]})
    p = IdxProvider(http=_client(handler))
    f = _run(p.financials("BBCA"))
    assert f.pe_ratio == 22.1
    assert f.price_to_book == 5.4
    assert f.net_interest_margin == 5.7
    assert f.non_performing_loan_ratio == 2.1
    assert f.capital_adequacy_ratio == 25.0
    assert f.loan_to_deposit_ratio == 78.4
    assert f.casa_ratio == 82.0


def test_dividends_parses_events():
    def handler(req):
        return httpx.Response(200, json={"data": [
            {"ExDate": "2025-06-15", "PaymentDate": "2025-07-15",
             "DividendPerShare": 145.0, "Currency": "IDR"},
            {"ExDate": "2024-06-10", "PaymentDate": "2024-07-10",
             "DividendPerShare": 130.0, "Currency": "IDR"},
        ]})
    p = IdxProvider(http=_client(handler))
    d = _run(p.dividends("BBCA"))
    assert d.symbol == "BBCA.JK"
    assert len(d.events) == 2
    assert d.events[0].amount_per_share == 145.0
    assert d.events[0].currency == "IDR"


def test_history_parses_candles():
    def handler(req):
        return httpx.Response(200, json={"data": [
            {"Date": "2025-08-01", "Open": 9400, "High": 9500,
             "Low": 9350, "Close": 9450, "Volume": 10_000_000},
            {"Date": "2025-08-02", "Open": 9450, "High": 9550,
             "Low": 9420, "Close": 9500, "Volume": 11_000_000},
        ]})
    p = IdxProvider(http=_client(handler))
    hs = _run(p.history("BBCA", "1mo", "1d"))
    assert len(hs) == 2
    assert hs[0].date == "2025-08-01"
    assert hs[1].close == 9500.0


def test_timeout_maps_correctly():
    def handler(req): raise httpx.TimeoutException("slow")
    p = IdxProvider(http=_client(handler))
    with pytest.raises(FinanceError) as ei:
        _run(p.quote("BBCA"))
    assert ei.value.code == ErrorCode.TIMEOUT


def test_provider_declares_capabilities_and_markets():
    p = IdxProvider(http=_client(lambda r: httpx.Response(200, json={})))
    assert p.name == "idx"
    assert p.tier == "scraped"
    assert p.markets == frozenset({"IDX"})
    for c in ("quote", "history", "company", "financials",
              "statements", "dividends", "corporate_actions", "sector"):
        assert c in p.capabilities
