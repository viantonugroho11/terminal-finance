"""Finance MCP server. Streamable-HTTP transport so Hermes-in-Docker can reach it."""
from __future__ import annotations
import os
from dataclasses import asdict
from mcp.server.fastmcp import FastMCP
from .providers.yahoo import YahooProvider
from . import technical as ta
from .portfolio import db as pdb, service as psvc, watchlist as pwl

mcp = FastMCP("finance-mcp")
market = YahooProvider()
fundamentals = YahooProvider()
news_provider = YahooProvider()
pdb.init()


@mcp.tool()
async def get_quote(symbol: str) -> dict:
    """Real-time quote for a stock/ETF/crypto symbol (e.g. NVDA, BTC-USD)."""
    q = await market.quote(symbol)
    return q.to_dict()


@mcp.tool()
async def get_history(symbol: str, period: str = "6mo", interval: str = "1d") -> dict:
    """OHLCV history. period: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max. interval: 1d,1wk,1mo."""
    candles = await market.history(symbol, period, interval)
    return {"symbol": symbol.upper(), "period": period, "interval": interval,
            "candles": [asdict(c) for c in candles]}


@mcp.tool()
async def get_company(symbol: str) -> dict:
    """Company profile: sector, industry, summary, market cap, employees."""
    return asdict(await fundamentals.company(symbol))


@mcp.tool()
async def get_financials(symbol: str) -> dict:
    """Fundamental ratios: P/E, P/B, ROE, margins, growth, D/E, FCF, dividend, beta."""
    return asdict(await fundamentals.financials(symbol))


@mcp.tool()
async def get_technical(symbol: str, period: str = "1y") -> dict:
    """Deterministic technical indicators: SMA(20/50/200), EMA20, RSI14, MACD, volatility, drawdown."""
    candles = await market.history(symbol, period, "1d")
    return {"symbol": symbol.upper(), "period": period, **ta.summary(candles)}


@mcp.tool()
async def search_news(query: str, limit: int = 10) -> dict:
    """Recent news for a symbol or query."""
    items = await news_provider.news(query, limit)
    return {"query": query, "items": [asdict(i) for i in items]}


@mcp.tool()
async def get_market_overview() -> dict:
    """Snapshot of major indices, crypto, and safe-haven assets."""
    symbols = {
        "S&P 500": "^GSPC", "NASDAQ": "^IXIC", "DOW": "^DJI",
        "BTC": "BTC-USD", "ETH": "ETH-USD",
        "GOLD": "GC=F", "OIL": "CL=F", "DXY": "DX-Y.NYB",
    }
    out: dict[str, dict | str] = {}
    for label, sym in symbols.items():
        try:
            q = await market.quote(sym)
            out[label] = q.to_dict()
        except Exception as e:
            out[label] = {"error": str(e)}
    return out


# ── portfolio ─────────────────────────────────────────────────────────────

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
    """Current positions with live prices, unrealized P&L, weights. Omit account for aggregate."""
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
        out.append({"symbol": s, "error": str(q)} if isinstance(q, Exception) else q.to_dict())
    return {"watchlist": name, "quotes": out}


def main() -> None:
    host = os.getenv("FINANCE_MCP_HOST", "0.0.0.0")
    port = int(os.getenv("FINANCE_MCP_PORT", "7800"))
    mcp.settings.host = host
    mcp.settings.port = port
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
