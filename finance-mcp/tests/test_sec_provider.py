"""SecProvider — mocked HTTP, no network."""
import asyncio

import httpx
import pytest
from finance_mcp.errors import ErrorCode, FinanceError
from finance_mcp.providers.sec import SecProvider, _pad_cik


def _client(handler):
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://data.sec.gov",
    )


def _run(coro): return asyncio.run(coro)


def test_pad_cik():
    assert _pad_cik(320193) == "0000320193"
    assert _pad_cik("320193") == "0000320193"
    assert _pad_cik("0000320193") == "0000320193"


def test_provider_declarations():
    p = SecProvider(http=_client(lambda r: httpx.Response(200, json={})),
                    ticker_map={"AAPL": 320193})
    assert p.name == "sec"
    assert p.tier == "primary"
    assert p.markets == frozenset({"US"})
    assert "sec:filings" in p.capabilities
    assert "sec:facts" in p.capabilities
    assert p.attribution.startswith("U.S. Securities")


def test_filings_uses_injected_ticker_map():
    def handler(req):
        assert "CIK0000320193.json" in req.url.path
        return httpx.Response(200, json={
            "name": "Apple Inc.",
            "filings": {"recent": {
                "accessionNumber":  ["0000320193-24-000123", "0000320193-24-000090"],
                "form":             ["10-K", "10-Q"],
                "filingDate":       ["2024-11-01", "2024-08-02"],
                "reportDate":       ["2024-09-28", "2024-06-29"],
                "primaryDocument":  ["aapl-20240928.htm", "aapl-20240629.htm"],
            }},
        })
    p = SecProvider(http=_client(handler), ticker_map={"AAPL": 320193})
    r = _run(p.sec_filings("AAPL", limit=5))
    assert r.symbol == "AAPL"
    assert r.cik == "0000320193"
    assert r.entity_name == "Apple Inc."
    assert len(r.items) == 2
    assert r.items[0].form == "10-K"
    assert r.items[0].url and "aapl-20240928.htm" in r.items[0].url


def test_filings_filter_by_form_type():
    def handler(req):
        return httpx.Response(200, json={"filings": {"recent": {
            "accessionNumber": ["a1", "a2", "a3"],
            "form":            ["10-K", "10-Q", "10-Q"],
            "filingDate":      ["2024-01-01", "2024-04-01", "2024-07-01"],
            "reportDate":      ["2023-12-31", "2024-03-31", "2024-06-30"],
            "primaryDocument": ["a.htm", "b.htm", "c.htm"],
        }}})
    p = SecProvider(http=_client(handler), ticker_map={"AAPL": 320193})
    r = _run(p.sec_filings("AAPL", form_type="10-Q"))
    assert len(r.items) == 2
    assert all(x.form == "10-Q" for x in r.items)


def test_unknown_ticker_raises_symbol_not_found():
    p = SecProvider(http=_client(lambda r: httpx.Response(200, json={})),
                    ticker_map={"AAPL": 320193})
    with pytest.raises(FinanceError) as ei:
        _run(p.sec_filings("NOSUCH"))
    assert ei.value.code == ErrorCode.SYMBOL_NOT_FOUND


def test_403_maps_authentication_failed():
    def handler(req): return httpx.Response(403, text="forbidden")
    p = SecProvider(http=_client(handler), ticker_map={"AAPL": 320193})
    with pytest.raises(FinanceError) as ei:
        _run(p.sec_filings("AAPL"))
    assert ei.value.code == ErrorCode.AUTHENTICATION_FAILED


def test_429_maps_rate_limited():
    def handler(req): return httpx.Response(429, text="slow down")
    p = SecProvider(http=_client(handler), ticker_map={"AAPL": 320193})
    with pytest.raises(FinanceError) as ei:
        _run(p.sec_filings("AAPL"))
    assert ei.value.code == ErrorCode.RATE_LIMITED
    assert ei.value.retry_after_seconds == 1


def test_facts_parses_xbrl_series():
    def handler(req):
        assert "companyfacts" in req.url.path
        return httpx.Response(200, json={"facts": {"us-gaap": {"Revenues": {
            "label": "Revenues", "description": "Total revenues",
            "units": {"USD": [
                {"val": 100e9, "end": "2023-09-30", "start": "2022-10-01",
                 "form": "10-K", "filed": "2023-11-01", "accn": "0000-1"},
                {"val": 110e9, "end": "2024-09-28", "start": "2023-10-01",
                 "form": "10-K", "filed": "2024-11-01", "accn": "0000-2"},
            ]},
        }}}})
    p = SecProvider(http=_client(handler), ticker_map={"AAPL": 320193})
    s = _run(p.sec_facts("AAPL", "Revenues"))
    assert s.symbol == "AAPL"
    assert s.concept == "Revenues"
    assert s.taxonomy == "us-gaap"
    assert len(s.observations) == 2
    assert s.observations[0].value == 100e9
    assert s.observations[0].unit == "USD"
    assert s.observations[-1].period_end == "2024-09-28"


def test_facts_unknown_concept_raises_data_unavailable():
    def handler(req):
        return httpx.Response(200, json={"facts": {"us-gaap": {}}})
    p = SecProvider(http=_client(handler), ticker_map={"AAPL": 320193})
    with pytest.raises(FinanceError) as ei:
        _run(p.sec_facts("AAPL", "NotAConcept"))
    assert ei.value.code == ErrorCode.DATA_UNAVAILABLE


def test_ticker_map_auto_loaded_when_not_injected():
    call_count = {"n": 0}
    def handler(req):
        call_count["n"] += 1
        if "company_tickers.json" in req.url.path:
            return httpx.Response(200, json={
                "0": {"cik_str": 320193, "ticker": "AAPL",
                      "title": "Apple Inc."},
            })
        return httpx.Response(200, json={"name": "Apple Inc.",
                                          "filings": {"recent": {}}})
    p = SecProvider(http=_client(handler))  # no ticker_map
    r = _run(p.sec_filings("AAPL"))
    assert r.cik == "0000320193"
    # Ticker map load + submissions fetch = 2 calls.
    assert call_count["n"] == 2
