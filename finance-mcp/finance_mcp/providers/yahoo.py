"""Yahoo Finance provider via yfinance. Scraping-based — swap for paid API in prod."""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import yfinance as yf
from ..models import (
    Quote, Candle, Company, Financials, NewsItem,
    IncomeStatement, BalanceSheet, CashFlowStatement, FinancialStatements,
    MarketOverview, MarketMovers, MoverItem,
)
from ..errors import FinanceError, ErrorCode, classify


def _run(fn, *a, **kw):
    return asyncio.get_event_loop().run_in_executor(None, lambda: fn(*a, **kw))


def _n(v):
    """Yahoo returns NaN as float('nan'); normalize to None so JSON is clean."""
    try:
        if v is None: return None
        f = float(v)
        return None if f != f else f  # NaN check
    except (TypeError, ValueError):
        return None


class YahooProvider:
    name = "yahoo"
    async def quote(self, symbol: str) -> Quote:
        try:
            t = yf.Ticker(symbol)
            info = await _run(lambda: t.fast_info)
            last = _n(info.last_price)
            prev = _n(info.previous_close)
            if last is None:
                raise FinanceError(ErrorCode.SYMBOL_NOT_FOUND,
                                   f"No quote data for {symbol}", provider="yahoo", symbol=symbol)
            change = (last - prev) if prev is not None else 0.0
            return Quote(
                symbol=symbol.upper(),
                price=last,
                change=change,
                change_percent=(change / prev * 100.0) if prev else 0.0,
                volume=int(info.last_volume or 0),
                currency=str(info.currency or "USD"),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        except FinanceError:
            raise
        except Exception as e:
            raise classify(e, provider="yahoo", symbol=symbol)

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

    async def financial_statements(self, symbol: str) -> FinancialStatements:
        t = yf.Ticker(symbol)
        try:
            inc_a  = await _run(lambda: t.income_stmt)
            bal_a  = await _run(lambda: t.balance_sheet)
            cf_a   = await _run(lambda: t.cashflow)
        except Exception as e:
            raise classify(e, provider="yahoo", symbol=symbol)

        def _income_row(col, df):
            g = lambda k: _n(df.loc[k, col]) if (df is not None and k in df.index) else None
            return IncomeStatement(
                period="annual", date=str(col.date() if hasattr(col, "date") else col),
                revenue=g("Total Revenue"), gross_profit=g("Gross Profit"),
                operating_income=g("Operating Income"), net_income=g("Net Income"),
                eps=g("Basic EPS") or g("Diluted EPS"),
            )
        def _bal_row(col, df):
            g = lambda k: _n(df.loc[k, col]) if (df is not None and k in df.index) else None
            return BalanceSheet(
                period="annual", date=str(col.date() if hasattr(col, "date") else col),
                total_assets=g("Total Assets"), total_liabilities=g("Total Liabilities Net Minority Interest"),
                total_equity=g("Stockholders Equity"), cash=g("Cash And Cash Equivalents"),
                total_debt=g("Total Debt"),
            )
        def _cf_row(col, df):
            g = lambda k: _n(df.loc[k, col]) if (df is not None and k in df.index) else None
            return CashFlowStatement(
                period="annual", date=str(col.date() if hasattr(col, "date") else col),
                operating_cash_flow=g("Operating Cash Flow"),
                investing_cash_flow=g("Investing Cash Flow"),
                financing_cash_flow=g("Financing Cash Flow"),
                free_cash_flow=g("Free Cash Flow"),
            )

        income  = [_income_row(c, inc_a) for c in (inc_a.columns if inc_a is not None else [])]
        balance = [_bal_row(c, bal_a)    for c in (bal_a.columns if bal_a is not None else [])]
        cash    = [_cf_row(c, cf_a)      for c in (cf_a.columns  if cf_a  is not None else [])]

        return FinancialStatements(symbol=symbol.upper(),
                                   income=income, balance=balance, cashflow=cash)

    async def market_overview(self) -> MarketOverview:
        buckets = {
            "indices":     {"S&P 500": "^GSPC", "NASDAQ": "^IXIC", "DOW": "^DJI", "Russell 2000": "^RUT", "VIX": "^VIX"},
            "crypto":      {"BTC": "BTC-USD", "ETH": "ETH-USD"},
            "commodities": {"GOLD": "GC=F", "OIL": "CL=F"},
            "fx":          {"DXY": "DX-Y.NYB"},
        }
        results: dict[str, dict[str, Quote]] = {k: {} for k in buckets}
        tasks = [
            (bucket, label, sym) for bucket, m in buckets.items() for label, sym in m.items()
        ]
        quotes = await asyncio.gather(*(self.quote(s) for _, _, s in tasks), return_exceptions=True)
        for (bucket, label, sym), q in zip(tasks, quotes):
            if isinstance(q, Quote):
                results[bucket][label] = q
        return MarketOverview(**results)

    async def market_movers(self) -> MarketMovers:
        # yfinance exposes premade screeners; guard because they change often.
        try:
            gainers = await _run(lambda: yf.screener.PredefinedScreener("day_gainers").response)
            losers  = await _run(lambda: yf.screener.PredefinedScreener("day_losers").response)
            active  = await _run(lambda: yf.screener.PredefinedScreener("most_actives").response)
        except Exception:
            # Fallback: leave empty rather than fabricating movers.
            raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                               "market movers screener not available from provider",
                               provider="yahoo")

        def _pack(payload) -> list[MoverItem]:
            items = ((payload or {}).get("finance") or {}).get("result", [{}])[0].get("quotes", [])
            out: list[MoverItem] = []
            for it in items[:10]:
                price = _n(it.get("regularMarketPrice"))
                if price is None: continue
                out.append(MoverItem(
                    symbol=it.get("symbol", ""), name=it.get("shortName"),
                    price=price, change=_n(it.get("regularMarketChange")) or 0.0,
                    change_percent=_n(it.get("regularMarketChangePercent")) or 0.0,
                    volume=int(it.get("regularMarketVolume") or 0),
                ))
            return out

        return MarketMovers(top_gainers=_pack(gainers),
                            top_losers=_pack(losers),
                            most_active=_pack(active))

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
