"""Normalized finance models. All providers return these — never provider-shaped dicts.

Every top-level response is wrapped in Provenance so Hermes can tell users
where the number came from and when. NEVER strip provenance for LLM prompts.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
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
    # Banking-specific (nullable — populated only for banks by providers
    # that supply them, e.g. OJK aggregates or bank annual reports).
    # See ADR-0020.
    net_interest_margin: float | None = None
    non_performing_loan_ratio: float | None = None
    capital_adequacy_ratio: float | None = None
    loan_to_deposit_ratio: float | None = None
    casa_ratio: float | None = None
    cost_of_credit: float | None = None
    loan_growth: float | None = None
    deposit_growth: float | None = None


@dataclass
class DividendEvent:
    ex_date: str
    payment_date: str | None
    amount_per_share: float
    currency: str


@dataclass
class DividendHistory:
    symbol: str
    events: list[DividendEvent] = field(default_factory=list)


@dataclass
class CorporateAction:
    date: str
    kind: str        # "split" | "reverse_split" | "rights_issue" | "bonus" | "dividend" | "other"
    ratio: str | None
    description: str | None


@dataclass
class CorporateActionHistory:
    symbol: str
    events: list[CorporateAction] = field(default_factory=list)


@dataclass
class MacroObservation:
    period: str          # ISO date or period label (e.g. "2025-Q2", "2025-07")
    value: float
    unit: str | None = None


@dataclass
class MacroSeries:
    indicator: str       # canonical name (e.g. "bi_rate", "cpi_yoy")
    source: str          # "bi" | "bps" | "ojk"
    unit: str | None     # "%", "IDR", "index", etc.
    observations: list[MacroObservation] = field(default_factory=list)
    frequency: str | None = None      # "daily" | "monthly" | "quarterly" | "annual"
    description: str | None = None
    attribution: str | None = None    # e.g. "Bank Indonesia", "BPS", "OJK SPI"


@dataclass
class SectorInfo:
    symbol: str
    sector_code: str | None      # IDX-IC code when known
    sector_name: str | None
    subsector: str | None
    industry: str | None
    sub_industry: str | None


@dataclass
class NewsItem:
    title: str
    publisher: str | None
    link: str
    published: str
    summary: str | None


@dataclass
class IncomeStatement:
    period: str          # "annual" | "quarterly"
    date: str            # ISO date of the report
    revenue: float | None
    gross_profit: float | None
    operating_income: float | None
    net_income: float | None
    eps: float | None


@dataclass
class BalanceSheet:
    period: str
    date: str
    total_assets: float | None
    total_liabilities: float | None
    total_equity: float | None
    cash: float | None
    total_debt: float | None


@dataclass
class CashFlowStatement:
    period: str
    date: str
    operating_cash_flow: float | None
    investing_cash_flow: float | None
    financing_cash_flow: float | None
    free_cash_flow: float | None


@dataclass
class FinancialStatements:
    symbol: str
    income: list[IncomeStatement] = field(default_factory=list)
    balance: list[BalanceSheet] = field(default_factory=list)
    cashflow: list[CashFlowStatement] = field(default_factory=list)


@dataclass
class MarketOverview:
    indices: dict[str, Quote] = field(default_factory=dict)
    crypto:  dict[str, Quote] = field(default_factory=dict)
    commodities: dict[str, Quote] = field(default_factory=dict)
    fx: dict[str, Quote] = field(default_factory=dict)


@dataclass
class MoverItem:
    symbol: str
    name: str | None
    price: float
    change: float
    change_percent: float
    volume: int


@dataclass
class MarketMovers:
    top_gainers: list[MoverItem] = field(default_factory=list)
    top_losers: list[MoverItem] = field(default_factory=list)
    most_active: list[MoverItem] = field(default_factory=list)


@dataclass
class Provenance:
    """Wrap every tool result so Hermes surfaces source + fetch time to the user."""
    data: Any
    source: str                                                # provider name
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    cache_hit: bool = False
    symbol: str | None = None
    resolver: dict[str, Any] | None = None                     # MarketContext.to_dict()
    attribution: str | None = None                             # e.g. "Data © IDX" for scraped sources

    def to_dict(self) -> dict[str, Any]:
        # Always deep-convert: handles dataclasses, nested dataclasses inside
        # lists/dicts, and passes primitives through unchanged.
        payload = _deep_asdict(self.data)
        prov: dict[str, Any] = {
            "source": self.source,
            "retrieved_at": self.retrieved_at,
            "cache_hit": self.cache_hit,
        }
        if self.symbol:
            prov["symbol"] = self.symbol
        if self.resolver:
            prov["resolver"] = self.resolver
        if self.attribution:
            prov["attribution"] = self.attribution
        return {"data": payload, "provenance": prov}


def _deep_asdict(obj: Any) -> Any:
    from dataclasses import is_dataclass, fields
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _deep_asdict(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, dict):
        return {k: _deep_asdict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_deep_asdict(v) for v in obj]
    return obj
