from finance_mcp.models import (
    Quote, MarketOverview, MarketMovers, MoverItem,
    FinancialStatements, IncomeStatement, BalanceSheet, CashFlowStatement,
    Provenance, _deep_asdict,
)


def _q():
    return Quote(symbol="NVDA", price=180.0, change=2.0, change_percent=1.12,
                 volume=1000, currency="USD", timestamp="2026-08-12T00:00:00Z")


def test_provenance_wraps_dataclass():
    p = Provenance(data=_q(), source="yahoo", cache_hit=True, symbol="NVDA")
    d = p.to_dict()
    assert d["data"]["symbol"] == "NVDA"
    assert d["data"]["price"] == 180.0
    assert d["provenance"]["source"] == "yahoo"
    assert d["provenance"]["cache_hit"] is True
    assert d["provenance"]["symbol"] == "NVDA"
    assert "retrieved_at" in d["provenance"]


def test_provenance_wraps_dict_untouched():
    p = Provenance(data={"a": 1, "b": [1, 2]}, source="mock")
    d = p.to_dict()
    assert d["data"] == {"a": 1, "b": [1, 2]}


def test_deep_asdict_handles_nested():
    fs = FinancialStatements(
        symbol="NVDA",
        income=[IncomeStatement("annual", "2025-01-31", 1000, 800, 500, 300, 1.2)],
        balance=[BalanceSheet("annual", "2025-01-31", 5000, 2000, 3000, 500, 1500)],
        cashflow=[CashFlowStatement("annual", "2025-01-31", 400, -100, -50, 350)],
    )
    d = _deep_asdict(fs)
    assert d["symbol"] == "NVDA"
    assert d["income"][0]["revenue"] == 1000
    assert d["balance"][0]["total_equity"] == 3000
    assert d["cashflow"][0]["free_cash_flow"] == 350


def test_market_overview_shape():
    mo = MarketOverview(indices={"SPX": _q()}, crypto={"BTC": _q()})
    d = _deep_asdict(mo)
    assert d["indices"]["SPX"]["symbol"] == "NVDA"
    assert d["commodities"] == {}


def test_market_movers_shape():
    mv = MarketMovers(top_gainers=[MoverItem("NVDA", "Nvidia", 180.0, 5.0, 2.8, 999)])
    d = _deep_asdict(mv)
    assert d["top_gainers"][0]["symbol"] == "NVDA"
    assert d["top_losers"] == []
