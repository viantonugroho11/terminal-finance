"""Yahoo Finance provider via yfinance. Scraping-based — swap for paid API in prod."""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import yfinance as yf
from ..models import Quote, Candle, Company, Financials, NewsItem


def _run(fn, *a, **kw):
    return asyncio.get_event_loop().run_in_executor(None, lambda: fn(*a, **kw))


class YahooProvider:
    async def quote(self, symbol: str) -> Quote:
        t = yf.Ticker(symbol)
        info = await _run(lambda: t.fast_info)
        last = float(info.last_price)
        prev = float(info.previous_close)
        change = last - prev
        return Quote(
            symbol=symbol.upper(),
            price=last,
            change=change,
            change_percent=(change / prev * 100.0) if prev else 0.0,
            volume=int(info.last_volume or 0),
            currency=str(info.currency or "USD"),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    async def history(self, symbol: str, period: str = "6mo", interval: str = "1d") -> list[Candle]:
        t = yf.Ticker(symbol)
        df = await _run(lambda: t.history(period=period, interval=interval, auto_adjust=False))
        out: list[Candle] = []
        for idx, row in df.iterrows():
            out.append(Candle(
                date=idx.strftime("%Y-%m-%d"),
                open=float(row["Open"]), high=float(row["High"]),
                low=float(row["Low"]), close=float(row["Close"]),
                volume=int(row["Volume"]),
            ))
        return out

    async def company(self, symbol: str) -> Company:
        t = yf.Ticker(symbol)
        info = await _run(lambda: t.info) or {}
        return Company(
            symbol=symbol.upper(),
            name=info.get("longName") or info.get("shortName") or symbol.upper(),
            sector=info.get("sector"),
            industry=info.get("industry"),
            country=info.get("country"),
            website=info.get("website"),
            employees=info.get("fullTimeEmployees"),
            summary=info.get("longBusinessSummary"),
            market_cap=info.get("marketCap"),
        )

    async def financials(self, symbol: str) -> Financials:
        t = yf.Ticker(symbol)
        info = await _run(lambda: t.info) or {}
        return Financials(
            symbol=symbol.upper(),
            pe_ratio=info.get("trailingPE"),
            forward_pe=info.get("forwardPE"),
            peg_ratio=info.get("pegRatio"),
            price_to_book=info.get("priceToBook"),
            price_to_sales=info.get("priceToSalesTrailing12Months"),
            profit_margin=info.get("profitMargins"),
            operating_margin=info.get("operatingMargins"),
            return_on_equity=info.get("returnOnEquity"),
            return_on_assets=info.get("returnOnAssets"),
            revenue_growth=info.get("revenueGrowth"),
            earnings_growth=info.get("earningsGrowth"),
            debt_to_equity=info.get("debtToEquity"),
            current_ratio=info.get("currentRatio"),
            free_cashflow=info.get("freeCashflow"),
            dividend_yield=info.get("dividendYield"),
            beta=info.get("beta"),
        )

    async def news(self, symbol_or_query: str, limit: int = 10) -> list[NewsItem]:
        t = yf.Ticker(symbol_or_query)
        items = await _run(lambda: t.news) or []
        out: list[NewsItem] = []
        for n in items[:limit]:
            content = n.get("content", n)
            out.append(NewsItem(
                title=content.get("title", ""),
                publisher=(content.get("provider") or {}).get("displayName") if isinstance(content.get("provider"), dict) else content.get("publisher"),
                link=(content.get("canonicalUrl") or {}).get("url", "") if isinstance(content.get("canonicalUrl"), dict) else content.get("link", ""),
                published=str(content.get("pubDate") or content.get("providerPublishTime", "")),
                summary=content.get("summary"),
            ))
        return out
