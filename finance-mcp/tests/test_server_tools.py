"""End-to-end MCP tool tests using MockProvider — no network."""
import asyncio
import os
import tempfile

os.environ["FINANCE_PROVIDER"] = "mock"
os.environ.setdefault("FINANCE_DB",
                      tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)

from finance_mcp import server  # noqa: E402


def _run(coro): return asyncio.run(coro)


def _payload(reply: dict) -> dict:
    """Server returns {data, provenance} on success or {error} on failure."""
    assert "error" not in reply, reply
    return reply["data"]


def test_provider_is_mock():
    assert server.provider.name == "mock"


def test_get_quote_returns_provenance_and_data():
    r = _run(server.get_quote("NVDA"))
    assert r["provenance"]["source"] == "mock"
    assert r["provenance"]["symbol"] == "NVDA"
    assert r["provenance"]["cache_hit"] is False
    d = _payload(r)
    assert d["symbol"] == "NVDA" and d["price"] > 0


def test_get_quote_second_call_cache_hits():
    server._c.cache.invalidate()
    r1 = _run(server.get_quote("AAPL"))
    r2 = _run(server.get_quote("AAPL"))
    assert r1["provenance"]["cache_hit"] is False
    assert r2["provenance"]["cache_hit"] is True
    assert r1["data"]["price"] == r2["data"]["price"]


def test_get_historical_prices_shape():
    r = _run(server.get_historical_prices("NVDA", "1mo", "1d"))
    d = _payload(r)
    assert len(d) == 22
    assert set(d[0].keys()) == {"date", "open", "high", "low", "close", "volume"}


def test_get_company_profile():
    d = _payload(_run(server.get_company_profile("MSFT")))
    assert d["symbol"] == "MSFT" and d["sector"] == "Technology"


def test_get_fundamentals():
    d = _payload(_run(server.get_fundamentals("GOOGL")))
    for k in ("pe_ratio", "profit_margin", "return_on_equity", "beta"):
        assert d[k] is not None


def test_get_financial_statements_three_years_each():
    d = _payload(_run(server.get_financial_statements("AMZN")))
    assert d["symbol"] == "AMZN"
    assert len(d["income"]) == 3
    assert len(d["balance"]) == 3
    assert len(d["cashflow"]) == 3
    assert d["income"][0]["revenue"] > 0


def test_get_market_overview_buckets_populated():
    d = _payload(_run(server.get_market_overview()))
    assert d["indices"] and d["crypto"] and d["commodities"] and d["fx"]


def test_get_market_movers_shape():
    d = _payload(_run(server.get_market_movers()))
    assert len(d["top_gainers"]) == 3
    assert len(d["top_losers"]) == 3
    assert len(d["most_active"]) == 3


def test_search_news_limit():
    d = _payload(_run(server.search_news("NVDA", limit=5)))
    assert len(d) == 5
    assert all(item["link"].startswith("https://") for item in d)


def test_get_technical_deterministic_keys():
    d = _payload(_run(server.get_technical("NVDA", "1y")))
    for k in ("sma_20", "sma_50", "sma_200", "rsi_14", "macd",
              "volatility_30d_annualized_pct", "max_drawdown_pct"):
        assert k in d


def test_aliases_match():
    server._c.cache.invalidate()
    a = _run(server.get_history("NVDA", "1mo", "1d"))["data"]
    b = _run(server.get_historical_prices("NVDA", "1mo", "1d"))["data"]
    assert a == b
    c = _run(server.get_financials("NVDA"))["data"]
    d = _run(server.get_fundamentals("NVDA"))["data"]
    assert c == d


def test_cache_stats_tool():
    server._c.cache.invalidate()
    _run(server.get_quote("TEST1"))
    _run(server.get_quote("TEST1"))
    st = _run(server.cache_stats())
    assert st["provider"] == "mock"
    assert st["cache"]["hits"] >= 1


def test_watchlist_quotes_errors_do_not_kill_batch():
    server._c.cache.invalidate()
    from finance_mcp.portfolio import watchlist
    watchlist.add("mix", "NVDA")
    watchlist.add("mix", "AAPL")
    r = _run(server.watchlist_quotes("mix"))
    assert r["watchlist"] == "mix"
    assert len(r["quotes"]) == 2
    for q in r["quotes"]:
        assert q["symbol"] in {"NVDA", "AAPL"}
        assert q.get("price") is not None
