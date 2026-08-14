"""Provider Protocols. Swap providers without touching tools.

Extended (ADR-0008 / ADR-0020) with capability + tier + market
declarations so the router (ADR-0012) can pick per-request.
"""
from __future__ import annotations
from typing import Protocol, Literal
from ..models import (
    Quote, Candle, Company, Financials, NewsItem,
    FinancialStatements, MarketOverview, MarketMovers,
)


Tier = Literal["primary", "aggregator", "scraped", "mock"]

# Canonical capability names. Providers advertise which they satisfy.
CAP_QUOTE         = "quote"
CAP_HISTORY       = "history"
CAP_COMPANY       = "company"
CAP_FINANCIALS    = "financials"
CAP_STATEMENTS    = "statements"
CAP_NEWS          = "news"
CAP_MARKET        = "market_overview"
CAP_MOVERS        = "market_movers"
CAP_DIVIDENDS     = "dividends"
CAP_CORP_ACTIONS  = "corporate_actions"
CAP_SECTOR        = "sector"

# IDX-specific microstructure + market-wide capabilities.
CAP_FOREIGN_FLOW      = "foreign_flow"
CAP_SEARCH            = "search"
CAP_BROKER_ACTIVITY   = "broker_activity"
CAP_ORDER_BOOK        = "order_book"
CAP_IPO_CALENDAR      = "ipo_calendar"
CAP_TRADING_CALENDAR  = "trading_calendar"
CAP_DISCLOSURES       = "disclosures"
CAP_BOARD             = "board"
CAP_SHAREHOLDERS      = "shareholders"
CAP_SUBSIDIARIES      = "subsidiaries"
CAP_IDX_OVERVIEW      = "idx_market_overview"
CAP_IDX_MOVERS        = "idx_market_movers"

# IDX flow deep-dive — ADR-0026.
CAP_INSIDER_TRADES         = "insider_trades"
CAP_MAJOR_HOLDER_CHANGES   = "major_holder_changes"
CAP_OWNERSHIP_BREAKDOWN    = "ownership_breakdown"
CAP_BROKER_FLOW_AGGREGATE  = "broker_flow_aggregate"

# SEC EDGAR (US primary source) — ADR-0018.
CAP_SEC_FILINGS       = "sec:filings"
CAP_SEC_FACTS         = "sec:facts"

# Macro capabilities — canonical indicator names live under macro:*.
CAP_MACRO_BI_RATE      = "macro:bi_rate"
CAP_MACRO_JISDOR       = "macro:jisdor"
CAP_MACRO_INFLATION    = "macro:inflation"
CAP_MACRO_GDP          = "macro:gdp"
CAP_MACRO_CPI          = "macro:cpi"
CAP_MACRO_UNEMPLOYMENT = "macro:unemployment"
CAP_MACRO_BANKING_SPI  = "macro:banking_spi"

# Canonical indicator → capability. Used by the macro dispatch tool.
MACRO_INDICATOR_TO_CAP: dict[str, str] = {
    "bi_rate":       CAP_MACRO_BI_RATE,
    "jisdor":        CAP_MACRO_JISDOR,
    "fx_usd_idr":    CAP_MACRO_JISDOR,
    "inflation":     CAP_MACRO_INFLATION,
    "cpi":           CAP_MACRO_CPI,
    "cpi_yoy":       CAP_MACRO_CPI,
    "gdp":           CAP_MACRO_GDP,
    "gdp_growth":    CAP_MACRO_GDP,
    "unemployment":  CAP_MACRO_UNEMPLOYMENT,
    "banking_spi":   CAP_MACRO_BANKING_SPI,
    "npl":           CAP_MACRO_BANKING_SPI,
    "car":           CAP_MACRO_BANKING_SPI,
    "credit_growth": CAP_MACRO_BANKING_SPI,
}


class MarketDataProvider(Protocol):
    name: str
    tier: Tier
    markets: frozenset[str]          # e.g. {"US","GLOBAL","ID","CRYPTO"}
    capabilities: frozenset[str]
    requires_api_key: bool
    async def quote(self, symbol: str) -> Quote: ...
    async def history(self, symbol: str, period: str, interval: str) -> list[Candle]: ...
    async def market_overview(self) -> MarketOverview: ...
    async def market_movers(self) -> MarketMovers: ...


class FundamentalProvider(Protocol):
    name: str
    tier: Tier
    markets: frozenset[str]
    capabilities: frozenset[str]
    requires_api_key: bool
    async def company(self, symbol: str) -> Company: ...
    async def financials(self, symbol: str) -> Financials: ...
    async def financial_statements(self, symbol: str) -> FinancialStatements: ...


class NewsProvider(Protocol):
    name: str
    tier: Tier
    markets: frozenset[str]
    capabilities: frozenset[str]
    requires_api_key: bool
    async def news(self, query: str, limit: int) -> list[NewsItem]: ...
