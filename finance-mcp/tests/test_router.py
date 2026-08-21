"""Router — ADR-0012 + ADR-0021."""
import asyncio

import pytest
from finance_mcp.errors import ErrorCode, FinanceError
from finance_mcp.router import Router


class _FakeProvider:
    def __init__(self, name, tier, markets, capabilities,
                 fails=False, fail_code=ErrorCode.PROVIDER_UNAVAILABLE):
        self.name = name
        self.tier = tier
        self.markets = frozenset(markets)
        self.capabilities = frozenset(capabilities)
        self.requires_api_key = False
        self.fails = fails
        self.fail_code = fail_code
        self.calls = 0

    async def quote(self, symbol):
        self.calls += 1
        if self.fails:
            raise FinanceError(self.fail_code, f"{self.name} fail",
                               provider=self.name, symbol=symbol)
        return {"symbol": symbol, "price": 1.0, "src": self.name}


def _run(coro): return asyncio.run(coro)


def _router_with(*providers):
    r = Router()
    for p in providers:
        r.register(p)
    return r


def test_idx_symbol_prefers_idx_provider():
    idx = _FakeProvider("idx", "scraped", {"IDX"}, {"quote", "history"})
    yh  = _FakeProvider("yahoo", "scraped", {"US", "IDX", "GLOBAL"}, {"quote", "history"})
    r = _router_with(idx, yh)

    async def _fetch(p): return await p.quote("BBCA")
    value, chosen, ctx = _run(r.call("quote", symbol="BBCA", fetch=_fetch))
    assert chosen.name == "idx"
    assert ctx.market == "IDX"
    assert idx.calls == 1 and yh.calls == 0


def test_us_symbol_prefers_yahoo():
    idx = _FakeProvider("idx", "scraped", {"IDX"}, {"quote"})
    yh  = _FakeProvider("yahoo", "scraped", {"US", "IDX", "GLOBAL"}, {"quote"})
    r = _router_with(idx, yh)

    async def _fetch(p): return await p.quote("AAPL")
    _, chosen, ctx = _run(r.call("quote", symbol="AAPL", fetch=_fetch))
    assert chosen.name == "yahoo"
    assert ctx.market == "US"


def test_falls_back_to_yahoo_when_idx_transient_fails():
    idx = _FakeProvider("idx", "scraped", {"IDX"}, {"quote"}, fails=True,
                        fail_code=ErrorCode.PROVIDER_UNAVAILABLE)
    yh  = _FakeProvider("yahoo", "scraped", {"US", "IDX"}, {"quote"})
    r = _router_with(idx, yh)

    async def _fetch(p): return await p.quote("BBCA")
    _, chosen, _ = _run(r.call("quote", symbol="BBCA", fetch=_fetch))
    assert chosen.name == "yahoo"
    assert idx.calls == 1 and yh.calls == 1


def test_stops_chain_on_symbol_not_found():
    idx = _FakeProvider("idx", "scraped", {"IDX"}, {"quote"}, fails=True,
                        fail_code=ErrorCode.SYMBOL_NOT_FOUND)
    yh  = _FakeProvider("yahoo", "scraped", {"US", "IDX"}, {"quote"})
    r = _router_with(idx, yh)

    async def _fetch(p): return await p.quote("BBCA")
    with pytest.raises(FinanceError) as ei:
        _run(r.call("quote", symbol="BBCA", fetch=_fetch))
    assert ei.value.code == ErrorCode.SYMBOL_NOT_FOUND
    assert yh.calls == 0


def test_no_provider_for_capability_raises():
    idx = _FakeProvider("idx", "scraped", {"IDX"}, {"quote"})
    r = _router_with(idx)

    async def _fetch(p): return await p.quote("AAPL")
    with pytest.raises(FinanceError) as ei:
        _run(r.call("quote", symbol="AAPL", fetch=_fetch))
    assert ei.value.code == ErrorCode.DATA_UNAVAILABLE


def test_chain_ordering_by_preference():
    idx = _FakeProvider("idx", "scraped", {"IDX"}, {"quote"})
    yh  = _FakeProvider("yahoo", "scraped", {"IDX"}, {"quote"})
    r = _router_with(yh, idx)  # registration order != preference order
    chain = r.chain("quote", "IDX")
    assert [p.name for p in chain] == ["idx", "yahoo"]


def test_unregistered_provider_dropped_from_chain():
    yh = _FakeProvider("yahoo", "scraped", {"IDX"}, {"quote"})
    r = _router_with(yh)
    chain = r.chain("quote", "IDX")
    assert [p.name for p in chain] == ["yahoo"]
