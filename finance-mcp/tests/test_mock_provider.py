import asyncio

from finance_mcp.providers.mock import MockProvider


def _run(coro): return asyncio.run(coro)


def test_quote_deterministic():
    p = MockProvider()
    a = _run(p.quote("NVDA")); b = _run(p.quote("NVDA"))
    assert a.symbol == "NVDA" == b.symbol
    assert a.price == b.price   # same seed → same price
    assert 10.0 <= a.price < 910.0


def test_quote_symbol_varies_price():
    p = MockProvider()
    assert _run(p.quote("NVDA")).price != _run(p.quote("AAPL")).price


def test_history_length_matches_period():
    p = MockProvider()
    assert len(_run(p.history("NVDA", "1mo", "1d"))) == 22
    assert len(_run(p.history("NVDA", "1y",  "1d"))) == 252


def test_company_and_financials_populated():
    p = MockProvider()
    c = _run(p.company("NVDA"))
    assert c.symbol == "NVDA" and c.sector and c.market_cap
    f = _run(p.financials("NVDA"))
    assert f.pe_ratio is not None and f.free_cashflow is not None


def test_financial_statements_three_years():
    p = MockProvider()
    fs = _run(p.financial_statements("NVDA"))
    assert len(fs.income) == 3 and len(fs.balance) == 3 and len(fs.cashflow) == 3
    # revenue grows
    revs = [i.revenue for i in fs.income]
    assert revs == sorted(revs)


def test_market_overview_has_all_buckets():
    mo = _run(MockProvider().market_overview())
    assert mo.indices and mo.crypto and mo.commodities and mo.fx


def test_market_movers_shape():
    mv = _run(MockProvider().market_movers())
    assert len(mv.top_gainers) == 3 and len(mv.top_losers) == 3 and len(mv.most_active) == 3
    assert all(m.change_percent > 0 for m in mv.top_gainers)
    assert all(m.change_percent < 0 for m in mv.top_losers)


def test_news_limit_respected():
    items = _run(MockProvider().news("NVDA", limit=5))
    assert len(items) == 5
    assert all(i.link.startswith("https://") for i in items)
