"""Finance MCP server.

Every tool: cache → retry → provider → normalize → provenance → return.
Errors surfaced as {"error": {code, message, ...}}, never fake defaults.
Streamable-HTTP transport so Hermes-in-Docker can reach us.
"""
from __future__ import annotations
import os
from typing import Any, Awaitable, Callable
from mcp.server.fastmcp import FastMCP

from . import cache as _c
from . import calc as _calc  # noqa: F401  (surfaced to importers; skill can reference)
from . import technical as ta
from .errors import FinanceError, ErrorCode, classify
from .logging_ import tool_call
from .models import Provenance, _deep_asdict
from .providers.mock import MockProvider
from .providers.yahoo import YahooProvider
from .portfolio import db as pdb, service as psvc, watchlist as pwl
from .retry import with_retry


def _pick_provider():
    kind = os.getenv("FINANCE_PROVIDER", "yahoo").lower()
    if kind == "mock":
        return MockProvider()
    return YahooProvider()


mcp = FastMCP("finance-mcp")
provider = _pick_provider()
fundamentals = provider
news_provider = provider
market = provider
pdb.init()


async def _do(
    tool: str, key: tuple, ttl: int,
    fetch: Callable[[], Awaitable[Any]],
    *, symbol: str | None = None,
) -> dict:
    """Cache + retry + log + wrap in provenance. Returns dict for MCP JSON reply."""
    with tool_call(tool, symbol=symbol, provider=provider.name) as ctx:
        try:
            value, hit = await _c.cache.get_or_fetch(
                key, ttl,
                lambda: with_retry(fetch, provider=provider.name, symbol=symbol),
            )
            if hit:
                ctx["hit"]()
            return Provenance(
                data=value, source=provider.name,
                cache_hit=hit, symbol=symbol,
            ).to_dict()
        except FinanceError as e:
            ctx["error"](e.code.value)
            return e.to_dict()
        except Exception as e:
            fe = classify(e, provider=provider.name, symbol=symbol)
            ctx["error"](fe.code.value)
            return fe.to_dict()


# ── market data ───────────────────────────────────────────────────────────

@mcp.tool()
async def get_quote(symbol: str) -> dict:
    """Real-time quote for a stock/ETF/crypto symbol (e.g. NVDA, BTC-USD)."""
    return await _do("get_quote", ("quote", symbol.upper()), _c.TTL_QUOTE,
                     lambda: market.quote(symbol), symbol=symbol)


@mcp.tool()
async def get_historical_prices(symbol: str, period: str = "6mo", interval: str = "1d") -> dict:
    """OHLCV history. period: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max. interval: 1d,1wk,1mo."""
    return await _do("get_historical_prices",
                     ("history", symbol.upper(), period, interval), _c.TTL_HISTORY,
                     lambda: market.history(symbol, period, interval), symbol=symbol)


@mcp.tool()
async def get_history(symbol: str, period: str = "6mo", interval: str = "1d") -> dict:
    """Alias for get_historical_prices (kept for skill backwards-compat)."""
    return await get_historical_prices(symbol, period, interval)


@mcp.tool()
async def get_company_profile(symbol: str) -> dict:
    """Company profile: sector, industry, summary, market cap, employees."""
    return await _do("get_company_profile", ("company", symbol.upper()), _c.TTL_COMPANY,
                     lambda: fundamentals.company(symbol), symbol=symbol)


@mcp.tool()
async def get_company(symbol: str) -> dict:
    """Alias for get_company_profile."""
    return await get_company_profile(symbol)


@mcp.tool()
async def get_fundamentals(symbol: str) -> dict:
    """Fundamental ratios: P/E, P/B, ROE, margins, growth, D/E, FCF, dividend, beta."""
    return await _do("get_fundamentals", ("fund", symbol.upper()), _c.TTL_FUNDAMENTALS,
                     lambda: fundamentals.financials(symbol), symbol=symbol)


@mcp.tool()
async def get_financials(symbol: str) -> dict:
    """Alias for get_fundamentals (kept for skill backwards-compat)."""
    return await get_fundamentals(symbol)


@mcp.tool()
async def get_financial_statements(symbol: str) -> dict:
    """Annual income statement, balance sheet, cash flow (up to 4y from provider)."""
    return await _do("get_financial_statements", ("stmts", symbol.upper()), _c.TTL_STATEMENTS,
                     lambda: fundamentals.financial_statements(symbol), symbol=symbol)


@mcp.tool()
async def get_technical(symbol: str, period: str = "1y") -> dict:
    """Deterministic technical indicators: SMA(20/50/200), EMA20, RSI14, MACD, volatility, drawdown."""
    async def _compute():
        candles = await market.history(symbol, period, "1d")
        return {"symbol": symbol.upper(), "period": period, **ta.summary(candles)}
    return await _do("get_technical", ("tech", symbol.upper(), period), _c.TTL_HISTORY,
                     _compute, symbol=symbol)


@mcp.tool()
async def get_market_overview() -> dict:
    """Snapshot of major indices, crypto, safe-haven assets."""
    return await _do("get_market_overview", ("overview",), _c.TTL_MARKET,
                     lambda: market.market_overview())


@mcp.tool()
async def get_market_movers() -> dict:
    """Top gainers, top losers, most active — from provider screener."""
    return await _do("get_market_movers", ("movers",), _c.TTL_MOVERS,
                     lambda: market.market_movers())


@mcp.tool()
async def search_news(query: str, limit: int = 10) -> dict:
    """Recent news for a symbol or query."""
    return await _do("search_news", ("news", query.upper(), limit), _c.TTL_NEWS,
                     lambda: news_provider.news(query, limit), symbol=query)


@mcp.tool()
async def cache_stats() -> dict:
    """Cache hits/misses/size — for diagnostics only."""
    return {"provider": provider.name, "cache": _c.cache.stats()}


# ── portfolio (Phase 4, unchanged shape) ──────────────────────────────────

@mcp.tool()
async def portfolio_add_transaction(account: str, symbol: str, side: str,
                                    quantity: float, price: float, fee: float = 0.0,
                                    executed_at: str | None = None,
                                    currency: str = "USD", note: str | None = None) -> dict:
    """Record a transaction. side ∈ {BUY,SELL,DIV,FEE,DEPOSIT,WITHDRAW}. executed_at ISO8601 or omit for now."""
    tid = psvc.add_transaction(account, symbol, side, quantity, price, fee,
                               executed_at, currency, note)
    return {"transaction_id": tid, "status": "recorded"}


@mcp.tool()
async def portfolio_holdings(account: str | None = None) -> dict:
    """Current positions with live prices, unrealized P&L, weights."""
    pos = await psvc.holdings(account)
    return {"account": account or "ALL", "positions": [p.__dict__ for p in pos]}


@mcp.tool()
async def portfolio_summary(account: str | None = None) -> dict:
    """Portfolio totals: market value, cost basis, unrealized P&L, realized income."""
    return await psvc.summary(account)


@mcp.tool()
async def portfolio_allocation(account: str | None = None) -> dict:
    """Sector allocation with % weights."""
    return await psvc.allocation(account)


@mcp.tool()
async def portfolio_risk(account: str | None = None) -> dict:
    """Risk: HHI concentration, top-5 weight, per-position 30d vol + 6mo drawdown."""
    return await psvc.risk(account)


# ── watchlists ────────────────────────────────────────────────────────────

@mcp.tool()
async def watchlist_create(name: str) -> dict:
    wid = pwl.create(name)
    return {"watchlist_id": wid, "name": name}


@mcp.tool()
async def watchlist_add(name: str, symbol: str) -> dict:
    pwl.add(name, symbol)
    return {"status": "added", "watchlist": name, "symbol": symbol.upper()}


@mcp.tool()
async def watchlist_remove(name: str, symbol: str) -> dict:
    pwl.remove(name, symbol)
    return {"status": "removed", "watchlist": name, "symbol": symbol.upper()}


@mcp.tool()
async def watchlist_list() -> dict:
    return {"watchlists": pwl.list_all()}


@mcp.tool()
async def watchlist_quotes(name: str) -> dict:
    """Live quotes for every symbol in a watchlist."""
    import asyncio
    syms = pwl.items(name)
    if not syms:
        return {"watchlist": name, "quotes": []}
    quotes = await asyncio.gather(*(market.quote(s) for s in syms), return_exceptions=True)
    out = []
    for s, q in zip(syms, quotes):
        if isinstance(q, Exception):
            fe = q if isinstance(q, FinanceError) else classify(q, provider=provider.name, symbol=s)
            out.append({"symbol": s, "error": fe.to_dict()["error"]})
        else:
            out.append(_deep_asdict(q))
    return {"watchlist": name, "quotes": out}


def main() -> None:
    host = os.getenv("FINANCE_MCP_HOST", "0.0.0.0")
    port = int(os.getenv("FINANCE_MCP_PORT", "7800"))
    mcp.settings.host = host
    mcp.settings.port = port
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
