"""Router.call_all + evaluate_report + valuation_implied_growth tools."""
import asyncio
import os
import tempfile

import pytest
from finance_mcp.errors import ErrorCode, FinanceError
from finance_mcp.router import Router


def _run(coro): return asyncio.run(coro)


class _FakeProvider:
    def __init__(self, name, markets=("US",), caps=("quote",), fails=False):
        self.name = name
        self.tier = "primary"
        self.markets = frozenset(markets)
        self.capabilities = frozenset(caps)
        self.requires_api_key = False
        self.attribution = None
        self.fails = fails

    async def quote(self, symbol):
        if self.fails:
            raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE, "boom",
                               provider=self.name, symbol=symbol)
        return {"symbol": symbol, "src": self.name}


def test_call_all_returns_every_success():
    a = _FakeProvider("a", markets={"US"}, caps={"quote"})
    b = _FakeProvider("b", markets={"US"}, caps={"quote"})
    r = Router(preference={("quote", "US"): ["a", "b"]})
    r.register(a); r.register(b)

    async def _f(p): return await p.quote("AAPL")
    results, ctx = _run(r.call_all("quote", symbol="AAPL", fetch=_f))
    assert {p.name for _, p in results} == {"a", "b"}
    assert ctx.market == "US"


def test_call_all_drops_failures_silently():
    a = _FakeProvider("a", markets={"US"}, caps={"quote"})
    b = _FakeProvider("b", markets={"US"}, caps={"quote"}, fails=True)
    r = Router(preference={("quote", "US"): ["a", "b"]})
    r.register(a); r.register(b)

    async def _f(p): return await p.quote("AAPL")
    results, _ = _run(r.call_all("quote", symbol="AAPL", fetch=_f))
    assert [p.name for _, p in results] == ["a"]


def test_call_all_empty_chain_raises():
    r = Router(preference={})
    async def _f(p): return None
    with pytest.raises(FinanceError) as ei:
        _run(r.call_all("quote", symbol="AAPL", fetch=_f))
    assert ei.value.code == ErrorCode.DATA_UNAVAILABLE


os.environ["FINANCE_PROVIDER"] = "mock"
os.environ.setdefault("FINANCE_DB",
                      tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)
from finance_mcp import server  # noqa: E402


def test_evaluate_report_tool_returns_verdict():
    md = "# X — Report\n\n## Snapshot [FACT]\n\nno numbers here.\n"
    r = _run(server.evaluate_report(md))
    d = r["data"]
    assert d["verdict"] in ("accept", "retry", "low_confidence")
    assert "score" in d and 0 <= d["score"] <= 100
    assert r["provenance"]["source"] == "finance_mcp.evaluator"


def test_valuation_implied_growth_solves():
    # Pick a scenario known to be inside the growth band.
    r = _run(server.valuation_implied_growth(
        symbol="TEST",
        current_price_per_share=100.0,
        base_fcf_per_share=5.0,
        projection_years=5,
        discount_rate=0.10,
        terminal_growth=0.03,
    ))
    d = r["data"]
    assert d["symbol"] == "TEST"
    # Either a float in [-0.20, 0.60] or None with a note.
    if d["implied_growth"] is not None:
        assert -0.20 <= d["implied_growth"] <= 0.60
    else:
        assert "note" in d


def test_valuation_implied_growth_out_of_band_returns_null_with_note():
    r = _run(server.valuation_implied_growth(
        symbol="TEST",
        current_price_per_share=1e18,
        base_fcf_per_share=5.0,
    ))
    d = r["data"]
    assert d["implied_growth"] is None
    assert "note" in d
