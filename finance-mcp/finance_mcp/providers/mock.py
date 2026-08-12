"""Deterministic mock provider — tests never touch the network.

Prices are seeded from a hash of the symbol so tests are stable across runs.
Set FINANCE_PROVIDER=mock to run the whole MCP against fake data.
"""
from __future__ import annotations
import hashlib
from datetime import datetime, timedelta, timezone
from ..models import (
    Quote, Candle, Company, Financials, NewsItem,
    IncomeStatement, BalanceSheet, CashFlowStatement, FinancialStatements,
    MarketOverview, MarketMovers, MoverItem,
)


def _seed(symbol: str) -> float:
    h = hashlib.sha256(symbol.upper().encode()).hexdigest()
    return (int(h[:8], 16) % 90_000) / 100.0 + 10.0  # 10.00 .. 909.99


class MockProvider:
    name = "mock"

    async def quote(self, symbol: str) -> Quote:
        price = _seed(symbol)
        change = round(price * 0.01, 4)
        return Quote(
            symbol=symbol.upper(), price=price, change=change,
            change_percent=round(change / price * 100, 4),
            volume=1_000_000, currency="USD",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    async def history(self, symbol: str, period: str = "6mo", interval: str = "1d") -> list[Candle]:
        base = _seed(symbol)
        n = {"1d": 1, "5d": 5, "1mo": 22, "3mo": 66, "6mo": 130, "1y": 252,
             "2y": 504, "5y": 1260, "max": 2520}.get(period, 130)
        out: list[Candle] = []
        start = datetime(2024, 1, 1)
        for i in range(n):
            drift = i * 0.05
            price = base + drift
            out.append(Candle(
                date=(start + timedelta(days=i)).strftime("%Y-%m-%d"),
                open=price, high=price + 1, low=price - 1, close=price,
                volume=1_000_000 + i,
            ))
        return out

    async def company(self, symbol: str) -> Company:
        return Company(
            symbol=symbol.upper(), name=f"{symbol.upper()} Corp",
            sector="Technology", industry="Semiconductors", country="US",
            website=f"https://example.com/{symbol.lower()}",
            employees=10_000, summary=f"Mock summary for {symbol.upper()}.",
            market_cap=_seed(symbol) * 1_000_000_000,
        )

    async def financials(self, symbol: str) -> Financials:
        s = _seed(symbol)
        return Financials(
            symbol=symbol.upper(), pe_ratio=s / 10, forward_pe=s / 12,
            peg_ratio=1.2, price_to_book=5.0, price_to_sales=8.0,
            profit_margin=0.25, operating_margin=0.30, return_on_equity=0.35,
            return_on_assets=0.15, revenue_growth=0.20, earnings_growth=0.25,
            debt_to_equity=0.40, current_ratio=1.8,
            free_cashflow=s * 100_000_000, dividend_yield=0.005, beta=1.1,
        )

    async def financial_statements(self, symbol: str) -> FinancialStatements:
        s = _seed(symbol)
        def _income(year: int, mult: float) -> IncomeStatement:
            rev = s * 100_000_000 * mult
            return IncomeStatement(
                period="annual", date=f"{year}-12-31",
                revenue=rev, gross_profit=rev * 0.7,
                operating_income=rev * 0.35, net_income=rev * 0.25,
                eps=rev * 0.25 / 1_000_000_000,
            )
        def _bal(year: int) -> BalanceSheet:
            return BalanceSheet(
                period="annual", date=f"{year}-12-31",
                total_assets=s * 1_000_000_000,
                total_liabilities=s * 400_000_000,
                total_equity=s * 600_000_000,
                cash=s * 200_000_000, total_debt=s * 150_000_000,
            )
        def _cf(year: int) -> CashFlowStatement:
            return CashFlowStatement(
                period="annual", date=f"{year}-12-31",
                operating_cash_flow=s * 120_000_000,
                investing_cash_flow=-s * 30_000_000,
                financing_cash_flow=-s * 40_000_000,
                free_cash_flow=s * 90_000_000,
            )
        return FinancialStatements(
            symbol=symbol.upper(),
            income=[_income(y, 1 + (y - 2023) * 0.15) for y in (2023, 2024, 2025)],
            balance=[_bal(y) for y in (2023, 2024, 2025)],
            cashflow=[_cf(y) for y in (2023, 2024, 2025)],
        )

    async def news(self, query: str, limit: int = 10) -> list[NewsItem]:
        return [
            NewsItem(
                title=f"Mock news {i} for {query.upper()}",
                publisher="MockWire", link=f"https://example.com/{query}/{i}",
                published=(datetime.now(timezone.utc) - timedelta(hours=i)).isoformat(),
                summary=f"Item {i} about {query}.",
            )
            for i in range(limit)
        ]

    async def market_overview(self) -> MarketOverview:
        async def q(s): return await self.quote(s)
        return MarketOverview(
            indices={"S&P 500": await q("^GSPC"), "NASDAQ": await q("^IXIC"),
                     "DOW": await q("^DJI")},
            crypto={"BTC": await q("BTC-USD"), "ETH": await q("ETH-USD")},
            commodities={"GOLD": await q("GC=F"), "OIL": await q("CL=F")},
            fx={"DXY": await q("DX-Y.NYB")},
        )

    async def market_movers(self) -> MarketMovers:
        def _mv(sym, pct):
            price = _seed(sym); change = price * pct / 100
            return MoverItem(symbol=sym, name=f"{sym} Corp", price=price,
                             change=change, change_percent=pct, volume=5_000_000)
        return MarketMovers(
            top_gainers=[_mv("AAA", 8.1), _mv("BBB", 6.4), _mv("CCC", 5.2)],
            top_losers=[_mv("XXX", -7.7), _mv("YYY", -5.1), _mv("ZZZ", -4.2)],
            most_active=[_mv("NVDA", 2.1), _mv("TSLA", -1.3), _mv("AAPL", 0.6)],
        )
