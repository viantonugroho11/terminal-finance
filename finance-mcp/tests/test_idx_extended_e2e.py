"""End-to-end IDX extended tools under FINANCE_PROVIDER=mock."""
import asyncio
import os
import tempfile

os.environ["FINANCE_PROVIDER"] = "mock"
os.environ.setdefault("FINANCE_DB",
                      tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)

from finance_mcp import server  # noqa: E402


def _run(coro): return asyncio.run(coro)


def _ok(r):
    assert "error" not in r, r
    return r["data"]


def test_get_foreign_flow():
    d = _ok(_run(server.get_foreign_flow("BBCA")))
    assert d["symbol"] in ("BBCA", "BBCA.JK")
    assert isinstance(d["days"], list) and d["days"]


def test_search_stocks():
    d = _ok(_run(server.search_stocks("bank", limit=5)))
    assert isinstance(d, list)
    assert d[0]["symbol"].endswith(".JK")


def test_get_broker_activity():
    d = _ok(_run(server.get_broker_activity("BBCA")))
    assert d["symbol"] in ("BBCA", "BBCA.JK")
    assert len(d["rows"]) == 2


def test_get_order_book():
    d = _ok(_run(server.get_order_book("BBCA", 5)))
    assert d["symbol"] in ("BBCA", "BBCA.JK")
    assert d["bids"] and d["asks"]


def test_get_ipo_calendar():
    d = _ok(_run(server.get_ipo_calendar()))
    assert d["events"][0]["symbol"] == "MOCK.JK"


def test_get_trading_calendar():
    d = _ok(_run(server.get_trading_calendar(2025)))
    assert d["year"] == 2025


def test_get_disclosures():
    d = _ok(_run(server.get_disclosures("BBCA")))
    assert d["items"][0]["category"] == "Financial Report"


def test_get_board():
    d = _ok(_run(server.get_board("BBCA")))
    assert d["commissioners"] and d["directors"]


def test_get_shareholders():
    d = _ok(_run(server.get_shareholders("BBCA")))
    assert len(d["holders"]) == 2
    assert d["holders"][0]["pct"] == 50.0


def test_get_subsidiaries():
    d = _ok(_run(server.get_subsidiaries("BBCA")))
    assert d["subsidiaries"][0]["ownership_pct"] == 99.9


def test_get_idx_overview():
    d = _ok(_run(server.get_idx_overview()))
    codes = {i["code"] for i in d["indices"]}
    assert "IHSG" in codes
    assert d["sectors"][0]["sector_name"] == "Financials"


def test_get_idx_movers():
    d = _ok(_run(server.get_idx_movers()))
    assert d["top_gainers"][0]["symbol"].endswith(".JK")
    assert len(d["top_losers"]) == 2
