"""Finance MCP server.

Every tool: resolver → router → cache → retry → provider → provenance → return.
Errors surfaced as {"error": {code, message, ...}}, never fake defaults.
Streamable-HTTP transport so Hermes-in-Docker can reach us.
"""
from __future__ import annotations
import os
from typing import Any, Awaitable, Callable
from mcp.server.fastmcp import FastMCP

from . import cache as _c
from . import calc as _calc  # noqa: F401
from . import technical as ta
from .errors import FinanceError, ErrorCode, classify
from .logging_ import tool_call
from .models import Provenance, _deep_asdict
from .providers.mock import MockProvider
from .providers.yahoo import YahooProvider
from .providers.idx import IdxProvider
from .providers.bi import BiProvider
from .providers.bps import BpsProvider
from .providers.ojk import OjkProvider
from .providers import MACRO_INDICATOR_TO_CAP
from .portfolio import db as pdb, service as psvc, watchlist as pwl
from .resolver import resolve as resolve_symbol
from .retry import with_retry
from .router import Router


def _build_router() -> Router:
    """Register providers. Overridable via FINANCE_PROVIDER=mock for tests."""
    r = Router()
    mode = os.getenv("FINANCE_PROVIDER", "auto").lower()
    if mode == "mock":
        r.register(MockProvider())
        return r
    r.register(YahooProvider())
    # IDX enabled by default; disable with FINANCE_IDX=off (e.g. in air-gapped tests).
    if os.getenv("FINANCE_IDX", "on").lower() != "off":
        r.register(IdxProvider())
    # Macro providers — enabled by default; each degrades cleanly on config gap.
    if os.getenv("FINANCE_BI", "on").lower() != "off":
        r.register(BiProvider())
    if os.getenv("FINANCE_BPS", "on").lower() != "off":
        r.register(BpsProvider())
    if os.getenv("FINANCE_OJK", "on").lower() != "off":
        r.register(OjkProvider())
    return r


mcp = FastMCP("finance-mcp")
router = _build_router()
pdb.init()


def _primary_name() -> str:
    """Best-effort name for cache_stats/legacy tests."""
    if any(p.name == "mock" for p in router.providers()):
        return "mock"
    if any(p.name == "yahoo" for p in router.providers()):
        return "yahoo"
    return next(iter(router.providers())).name if router.providers() else "unknown"


# Back-compat alias: some existing tests import `server.provider`.
class _ProviderProxy:
    @property
    def name(self) -> str: return _primary_name()

    async def quote(self, symbol: str):
        # Preserve the pre-router behavior used by `watchlist_quotes`.
        async def _fetch(p): return await p.quote(symbol)
        value, _, _ = await router.call("quote", symbol=symbol, fetch=_fetch)
        return value


provider = _ProviderProxy()


async def _do(
    tool: str,
    capability: str,
    key_extra: tuple,
    ttl: int,
    fetch: Callable[[Any], Awaitable[Any]],
    *,
    symbol: str | None = None,
    market: str | None = None,
) -> dict:
    """Router-driven: resolve symbol, pick provider, cache, retry, wrap."""
    with tool_call(tool, symbol=symbol, provider="router") as ctx:
        try:
            ctx_key_market = market
            if symbol is not None and ctx_key_market is None:
                ctx_key_market = resolve_symbol(symbol).market
            # Cache key includes market so cross-market symbol collisions
            # (rare, but possible) never bleed.
            cache_key = (tool, ctx_key_market or "-", *key_extra)

            hit = _c.cache.get(cache_key)
            if hit is not None:
                value, prov_name, mctx_dict = hit
                ctx["hit"]()
                return Provenance(
                    data=value, source=prov_name,
                    cache_hit=True, symbol=symbol,
                    resolver=mctx_dict,
                ).to_dict()

            async def _routed():
                async def _one(provider):
                    return await with_retry(lambda: fetch(provider),
                                            provider=provider.name,
                                            symbol=symbol)
                return await router.call(
                    capability, symbol=symbol, market=market, fetch=_one,
                )

            value, chosen, mctx = await _routed()
            mctx_dict = mctx.to_dict() if mctx else None
            _c.cache.set(cache_key, (value, chosen.name, mctx_dict), ttl)
            return Provenance(
                data=value, source=chosen.name,
                cache_hit=False, symbol=symbol,
                resolver=mctx_dict,
            ).to_dict()
        except FinanceError as e:
            ctx["error"](e.code.value)
            return e.to_dict()
        except Exception as e:
            fe = classify(e, provider="router", symbol=symbol)
            ctx["error"](fe.code.value)
            return fe.to_dict()


# ── market data ───────────────────────────────────────────────────────────

@mcp.tool()
async def get_quote(symbol: str) -> dict:
    """Real-time quote. Auto-detects market (US/IDX/crypto) — no suffix needed for known IDX tickers."""
    return await _do("get_quote", "quote", (symbol.upper(),), _c.TTL_QUOTE,
                     lambda p: p.quote(symbol), symbol=symbol)


@mcp.tool()
async def get_historical_prices(symbol: str, period: str = "6mo", interval: str = "1d") -> dict:
    """OHLCV history. period: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max. interval: 1d,1wk,1mo."""
    return await _do("get_historical_prices", "history",
                     (symbol.upper(), period, interval), _c.TTL_HISTORY,
                     lambda p: p.history(symbol, period, interval), symbol=symbol)


@mcp.tool()
async def get_history(symbol: str, period: str = "6mo", interval: str = "1d") -> dict:
    """Alias for get_historical_prices."""
    return await get_historical_prices(symbol, period, interval)


@mcp.tool()
async def get_company_profile(symbol: str) -> dict:
    """Company profile: sector, industry, summary, market cap, employees."""
    return await _do("get_company_profile", "company",
                     (symbol.upper(),), _c.TTL_COMPANY,
                     lambda p: p.company(symbol), symbol=symbol)


@mcp.tool()
async def get_company(symbol: str) -> dict:
    """Alias for get_company_profile."""
    return await get_company_profile(symbol)


@mcp.tool()
async def get_fundamentals(symbol: str) -> dict:
    """Fundamental ratios. For IDX banks also includes NIM/NPL/CAR/LDR/CASA when the provider supplies them."""
    return await _do("get_fundamentals", "financials",
                     (symbol.upper(),), _c.TTL_FUNDAMENTALS,
                     lambda p: p.financials(symbol), symbol=symbol)


@mcp.tool()
async def get_financials(symbol: str) -> dict:
    """Alias for get_fundamentals."""
    return await get_fundamentals(symbol)


@mcp.tool()
async def get_financial_statements(symbol: str) -> dict:
    """Annual income statement, balance sheet, cash flow."""
    return await _do("get_financial_statements", "statements",
                     (symbol.upper(),), _c.TTL_STATEMENTS,
                     lambda p: p.financial_statements(symbol), symbol=symbol)


@mcp.tool()
async def get_dividends(symbol: str) -> dict:
    """Dividend history (ex-date, payment date, per-share amount, currency)."""
    return await _do("get_dividends", "dividends",
                     (symbol.upper(),), _c.TTL_DIVIDENDS,
                     lambda p: p.dividends(symbol), symbol=symbol)


@mcp.tool()
async def get_corporate_actions(symbol: str) -> dict:
    """Corporate actions: splits, rights issues, bonus shares, dividends."""
    return await _do("get_corporate_actions", "corporate_actions",
                     (symbol.upper(),), _c.TTL_CORP_ACTIONS,
                     lambda p: p.corporate_actions(symbol), symbol=symbol)


@mcp.tool()
async def get_sector_info(symbol: str) -> dict:
    """Sector / industry classification. For IDX, returns IDX-IC taxonomy when available."""
    return await _do("get_sector_info", "sector",
                     (symbol.upper(),), _c.TTL_SECTOR,
                     lambda p: p.sector(symbol), symbol=symbol)


@mcp.tool()
async def get_technical(symbol: str, period: str = "1y") -> dict:
    """Deterministic technical indicators: SMA(20/50/200), EMA20, RSI14, MACD, volatility, drawdown."""
    async def _compute(p):
        candles = await p.history(symbol, period, "1d")
        return {"symbol": symbol.upper(), "period": period, **ta.summary(candles)}
    return await _do("get_technical", "history",
                     (symbol.upper(), period), _c.TTL_HISTORY,
                     _compute, symbol=symbol)


@mcp.tool()
async def get_market_overview() -> dict:
    """Snapshot of major indices, crypto, safe-haven assets."""
    return await _do("get_market_overview", "market_overview",
                     (), _c.TTL_MARKET,
                     lambda p: p.market_overview(), market="US")


@mcp.tool()
async def get_market_movers() -> dict:
    """Top gainers, top losers, most active."""
    return await _do("get_market_movers", "market_movers",
                     (), _c.TTL_MOVERS,
                     lambda p: p.market_movers(), market="US")


@mcp.tool()
async def search_news(query: str, limit: int = 10) -> dict:
    """Recent news for a symbol or query."""
    return await _do("search_news", "news",
                     (query.upper(), limit), _c.TTL_NEWS,
                     lambda p: p.news(query, limit), symbol=query)


@mcp.tool()
async def cache_stats() -> dict:
    """Cache hits/misses/size + registered providers — diagnostics only."""
    return {
        "provider": _primary_name(),
        "providers": [
            {"name": p.name, "tier": getattr(p, "tier", "?"),
             "markets": sorted(getattr(p, "markets", []))}
            for p in router.providers()
        ],
        "cache": _c.cache.stats(),
    }


@mcp.tool()
async def get_foreign_flow(symbol: str) -> dict:
    """IDX foreign investor net flow per day (last ~30 days)."""
    return await _do("get_foreign_flow", "foreign_flow",
                     (symbol.upper(),), _c.TTL_FOREIGN_FLOW,
                     lambda p: p.foreign_flow(symbol), symbol=symbol)


@mcp.tool()
async def search_stocks(query: str, limit: int = 20) -> dict:
    """Search IDX listed companies by name or code fragment."""
    return await _do("search_stocks", "search",
                     (query.upper(), limit), _c.TTL_SEARCH,
                     lambda p: p.search(query, limit), market="IDX")


@mcp.tool()
async def get_broker_activity(symbol: str, date: str | None = None) -> dict:
    """Broker buy/sell summary for an IDX symbol (per broker code)."""
    return await _do("get_broker_activity", "broker_activity",
                     (symbol.upper(), date or "latest"), _c.TTL_BROKER,
                     lambda p: p.broker_activity(symbol, date), symbol=symbol)


@mcp.tool()
async def get_order_book(symbol: str, depth: int = 10) -> dict:
    """Current bid/ask depth for an IDX symbol."""
    return await _do("get_order_book", "order_book",
                     (symbol.upper(), depth), _c.TTL_ORDER_BOOK,
                     lambda p: p.order_book(symbol, depth), symbol=symbol)


@mcp.tool()
async def get_ipo_calendar() -> dict:
    """Recent + upcoming IDX new listings (IPOs)."""
    return await _do("get_ipo_calendar", "ipo_calendar",
                     (), _c.TTL_IPO,
                     lambda p: p.ipo_calendar(), market="IDX")


@mcp.tool()
async def get_trading_calendar(year: int) -> dict:
    """IDX trading calendar for a given year (holidays + trading days)."""
    return await _do("get_trading_calendar", "trading_calendar",
                     (year,), _c.TTL_CALENDAR,
                     lambda p: p.trading_calendar(year), market="IDX")


@mcp.tool()
async def get_disclosures(symbol: str, limit: int = 20) -> dict:
    """Company disclosures / announcements filed to IDX."""
    return await _do("get_disclosures", "disclosures",
                     (symbol.upper(), limit), _c.TTL_DISCLOSURES,
                     lambda p: p.disclosures(symbol, limit), symbol=symbol)


@mcp.tool()
async def get_board(symbol: str) -> dict:
    """Board of Commissioners + Board of Directors for an IDX company."""
    return await _do("get_board", "board",
                     (symbol.upper(),), _c.TTL_BOARD,
                     lambda p: p.board(symbol), symbol=symbol)


@mcp.tool()
async def get_shareholders(symbol: str) -> dict:
    """Major shareholders (name, kind, shares, %)."""
    return await _do("get_shareholders", "shareholders",
                     (symbol.upper(),), _c.TTL_SHAREHOLDERS,
                     lambda p: p.shareholders(symbol), symbol=symbol)


@mcp.tool()
async def get_subsidiaries(symbol: str) -> dict:
    """Company subsidiaries with ownership % and business line."""
    return await _do("get_subsidiaries", "subsidiaries",
                     (symbol.upper(),), _c.TTL_SUBSIDIARIES,
                     lambda p: p.subsidiaries(symbol), symbol=symbol)


@mcp.tool()
async def get_idx_overview() -> dict:
    """IDX indices (IHSG, LQ45, …) + sector performance."""
    return await _do("get_idx_overview", "idx_market_overview",
                     (), _c.TTL_IDX_OVERVIEW,
                     lambda p: p.idx_market_overview(), market="IDX")


@mcp.tool()
async def get_idx_movers() -> dict:
    """IDX top gainers / losers / most active."""
    return await _do("get_idx_movers", "idx_market_movers",
                     (), _c.TTL_IDX_MOVERS,
                     lambda p: p.idx_market_movers(), market="IDX")


@mcp.tool()
async def get_macro(indicator: str) -> dict:
    """Indonesian macro indicator. Names: bi_rate, jisdor (USD/IDR), inflation, cpi, gdp, unemployment, banking_spi (NPL/CAR via OJK)."""
    ind = indicator.strip().lower()
    cap = MACRO_INDICATOR_TO_CAP.get(ind)
    if cap is None:
        return FinanceError(
            ErrorCode.DATA_UNAVAILABLE,
            f"Unknown macro indicator {indicator!r}. "
            f"Known: {sorted(MACRO_INDICATOR_TO_CAP)}",
            provider="router",
        ).to_dict()
    ttl = _c.TTL_MACRO_DAILY if ind in ("bi_rate", "jisdor", "fx_usd_idr") \
        else _c.TTL_MACRO_MONTHLY
    return await _do(
        "get_macro", cap, (ind,), ttl,
        lambda p: p.macro_indicator(ind),
        market="MACRO",
    )


@mcp.tool()
async def resolve_symbol_tool(symbol: str) -> dict:
    """Show how the resolver would classify a symbol. Diagnostics."""
    return {"symbol": symbol, "resolved": resolve_symbol(symbol).to_dict()}


# ── portfolio (unchanged) ─────────────────────────────────────────────────

@mcp.tool()
async def portfolio_add_transaction(account: str, symbol: str, side: str,
                                    quantity: float, price: float, fee: float = 0.0,
                                    executed_at: str | None = None,
                                    currency: str = "USD", note: str | None = None) -> dict:
    """Record a transaction. side ∈ {BUY,SELL,DIV,FEE,DEPOSIT,WITHDRAW}."""
    tid = psvc.add_transaction(account, symbol, side, quantity, price, fee,
                               executed_at, currency, note)
    return {"transaction_id": tid, "status": "recorded"}


@mcp.tool()
async def portfolio_holdings(account: str | None = None) -> dict:
    pos = await psvc.holdings(account)
    return {"account": account or "ALL", "positions": [p.__dict__ for p in pos]}


@mcp.tool()
async def portfolio_summary(account: str | None = None) -> dict:
    return await psvc.summary(account)


@mcp.tool()
async def portfolio_allocation(account: str | None = None) -> dict:
    return await psvc.allocation(account)


@mcp.tool()
async def portfolio_risk(account: str | None = None) -> dict:
    return await psvc.risk(account)


# ── watchlists ────────────────────────────────────────────────────────────

@mcp.tool()
async def watchlist_create(name: str) -> dict:
    return {"watchlist_id": pwl.create(name), "name": name}


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
    import asyncio
    syms = pwl.items(name)
    if not syms:
        return {"watchlist": name, "quotes": []}
    async def _q(s):
        try:
            return await provider.quote(s)
        except Exception as e:
            return e
    quotes = await asyncio.gather(*(_q(s) for s in syms), return_exceptions=True)
    out = []
    for s, q in zip(syms, quotes):
        if isinstance(q, Exception):
            fe = q if isinstance(q, FinanceError) else classify(q, provider="router", symbol=s)
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
