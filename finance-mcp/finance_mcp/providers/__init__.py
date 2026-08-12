"""Provider interfaces. Swap Yahoo for Polygon/AlphaVantage/etc. without touching tools."""
from __future__ import annotations
from typing import Protocol
from ..models import Quote, Candle, Company, Financials, NewsItem


class MarketDataProvider(Protocol):
    async def quote(self, symbol: str) -> Quote: ...
    async def history(self, symbol: str, period: str, interval: str) -> list[Candle]: ...


class FundamentalProvider(Protocol):
    async def company(self, symbol: str) -> Company: ...
    async def financials(self, symbol: str) -> Financials: ...


class NewsProvider(Protocol):
    async def search(self, query: str, limit: int) -> list[NewsItem]: ...
