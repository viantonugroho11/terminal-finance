"""Provider Protocols. Swap Yahoo for Polygon/AlphaVantage/etc. without touching tools."""
from __future__ import annotations
from typing import Protocol
from ..models import (
    Quote, Candle, Company, Financials, NewsItem,
    FinancialStatements, MarketOverview, MarketMovers,
)


class MarketDataProvider(Protocol):
    name: str
    async def quote(self, symbol: str) -> Quote: ...
    async def history(self, symbol: str, period: str, interval: str) -> list[Candle]: ...
    async def market_overview(self) -> MarketOverview: ...
    async def market_movers(self) -> MarketMovers: ...


class FundamentalProvider(Protocol):
    name: str
    async def company(self, symbol: str) -> Company: ...
    async def financials(self, symbol: str) -> Financials: ...
    async def financial_statements(self, symbol: str) -> FinancialStatements: ...


class NewsProvider(Protocol):
    name: str
    async def news(self, query: str, limit: int) -> list[NewsItem]: ...
