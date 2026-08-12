"""Normalized finance models. All providers return these — never provider-shaped dicts."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any


@dataclass
class Quote:
    symbol: str
    price: float
    change: float
    change_percent: float
    volume: int
    currency: str
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Candle:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class Company:
    symbol: str
    name: str
    sector: str | None
    industry: str | None
    country: str | None
    website: str | None
    employees: int | None
    summary: str | None
    market_cap: float | None


@dataclass
class Financials:
    symbol: str
    pe_ratio: float | None
    forward_pe: float | None
    peg_ratio: float | None
    price_to_book: float | None
    price_to_sales: float | None
    profit_margin: float | None
    operating_margin: float | None
    return_on_equity: float | None
    return_on_assets: float | None
    revenue_growth: float | None
    earnings_growth: float | None
    debt_to_equity: float | None
    current_ratio: float | None
    free_cashflow: float | None
    dividend_yield: float | None
    beta: float | None


@dataclass
class NewsItem:
    title: str
    publisher: str | None
    link: str
    published: str
    summary: str | None
