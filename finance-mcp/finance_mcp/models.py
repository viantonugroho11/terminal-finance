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


# ── IDX market-microstructure extensions ─────────────────────────────

@dataclass
class ForeignFlowDay:
    date: str
    buy_value: float | None
    sell_value: float | None
    net_value: float | None
    currency: str = "IDR"


@dataclass
class ForeignFlow:
    symbol: str
    days: list[ForeignFlowDay] = field(default_factory=list)


@dataclass
class SearchResult:
    symbol: str
    name: str
    sector: str | None = None
    market: str = "IDX"


@dataclass
class BrokerActivityRow:
    broker_code: str
    broker_name: str | None
    buy_lot: int | None
    sell_lot: int | None
    buy_value: float | None
    sell_value: float | None
    net_value: float | None


@dataclass
class BrokerActivity:
    symbol: str
    date: str
    rows: list[BrokerActivityRow] = field(default_factory=list)


@dataclass
class OrderBookLevel:
    price: float
    volume: int
    orders: int | None = None


@dataclass
class OrderBook:
    symbol: str
    timestamp: str
    bids: list[OrderBookLevel] = field(default_factory=list)
    asks: list[OrderBookLevel] = field(default_factory=list)


@dataclass
class IpoEvent:
    symbol: str
    name: str
    listing_date: str
    offer_price: float | None
    shares_offered: int | None
    sector: str | None = None


@dataclass
class IpoCalendar:
    events: list[IpoEvent] = field(default_factory=list)


@dataclass
class TradingCalendarDay:
    date: str
    is_trading_day: bool
    holiday_name: str | None = None


@dataclass
class TradingCalendar:
    year: int
    days: list[TradingCalendarDay] = field(default_factory=list)


@dataclass
class DisclosureItem:
    date: str
    title: str
    category: str | None
    url: str | None


@dataclass
class DisclosureFeed:
    symbol: str
    items: list[DisclosureItem] = field(default_factory=list)


@dataclass
class BoardMember:
    name: str
    position: str
    since: str | None = None


@dataclass
class Board:
    symbol: str
    commissioners: list[BoardMember] = field(default_factory=list)
    directors: list[BoardMember] = field(default_factory=list)


@dataclass
class ShareholderEntry:
    name: str
    kind: str | None          # "individual" | "institution" | "government"
    shares: int | None
    pct: float | None


@dataclass
class Shareholders:
    symbol: str
    holders: list[ShareholderEntry] = field(default_factory=list)


@dataclass
class Subsidiary:
    name: str
    ownership_pct: float | None
    business: str | None


@dataclass
class SubsidiaryList:
    symbol: str
    subsidiaries: list[Subsidiary] = field(default_factory=list)


# ── IDX market-wide (index / sector / movers) ─────────────────────────

@dataclass
class IndexQuote:
    code: str                   # e.g. "IHSG", "LQ45"
    value: float
    change: float
    change_percent: float
    volume: int | None
    value_traded: float | None  # nominal traded value (IDR)
    timestamp: str


@dataclass
class SectorPerf:
    sector_code: str
    sector_name: str
    change_percent: float
    value_traded: float | None = None


@dataclass
class IdxMarketOverview:
    indices: list[IndexQuote] = field(default_factory=list)
    sectors: list[SectorPerf] = field(default_factory=list)


# ── SEC EDGAR (US primary source, ADR-0018) ──────────────────────────

@dataclass
class SecFiling:
    accession_no: str
    form: str                     # "10-K", "10-Q", "8-K", "4", "13F-HR", ...
    filed_date: str
    report_date: str | None
    primary_document: str | None
    url: str | None


@dataclass
class SecFilings:
    symbol: str
    cik: str
    entity_name: str | None
    items: list[SecFiling] = field(default_factory=list)


@dataclass
class SecFactObservation:
    value: float
    unit: str
    period_end: str
    period_start: str | None
    form: str | None              # form that reported it (10-K/10-Q)
    filed_date: str | None
    accession_no: str | None


@dataclass
class SecFactSeries:
    symbol: str
    cik: str
    concept: str                  # e.g. "Revenues", "NetIncomeLoss"
    taxonomy: str                 # "us-gaap" | "dei" | "ifrs-full"
    label: str | None
    description: str | None
    observations: list[SecFactObservation] = field(default_factory=list)


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


# ── ADR-0026: IDX flow deep-dive ───────────────────────────────────

@dataclass
class InsiderTrade:
    symbol: str
    date: str              # ISO date
    name: str              # insider name
    role: str | None       # director, commissioner, controlling shareholder
    side: str              # BUY | SELL
    qty: int
    price: float | None
    total_value: float | None
    source_url: str | None = None


@dataclass
class InsiderTradeList:
    symbol: str
    days: int
    trades: list[InsiderTrade] = field(default_factory=list)


@dataclass
class HolderChange:
    symbol: str
    date: str
    holder_name: str
    pct_before: float | None
    pct_after: float | None
    change_pct: float | None      # +/− pct points
    source_url: str | None = None


@dataclass
class HolderChangeList:
    symbol: str
    days: int
    changes: list[HolderChange] = field(default_factory=list)


@dataclass
class OwnershipBreakdown:
    symbol: str
    as_of: str
    foreign_pct: float | None
    domestic_pct: float | None
    local_institutional_pct: float | None
    retail_pct: float | None
    total_shares: int | None = None


@dataclass
class BrokerAggRow:
    broker_code: str
    broker_name: str | None
    net_value: float
    buy_value: float | None = None
    sell_value: float | None = None
    days_active: int = 0


@dataclass
class BrokerFlowAggregate:
    symbol: str
    days: int
    top_net_buyers: list[BrokerAggRow] = field(default_factory=list)
    top_net_sellers: list[BrokerAggRow] = field(default_factory=list)


@dataclass
class Provenance:
    """Wrap every tool result so Hermes surfaces source + fetch time to the user.

    Envelope shape (see ADR-0004, ADR-0010, ADR-0011):
      {
        "data": <normalized payload>,
        "provenance": {
          "source":        provider name (e.g. "idx", "yahoo", "bi"),
          "tier":          "primary" | "aggregator" | "scraped" | "mock",
          "schema_version": SCHEMA_VERSION,
          "retrieved_at":  ISO-8601 UTC,
          "cache_hit":     bool,
          "symbol":        optional canonical/raw symbol,
          "resolver":      optional MarketContext dict,
          "attribution":   optional human-readable source credit
        }
      }
    """
    data: Any
    source: str                                                # provider name
    tier: str | None = None                                    # provider tier — ADR-0011
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    cache_hit: bool = False
    symbol: str | None = None
    resolver: dict[str, Any] | None = None                     # MarketContext.to_dict()
    attribution: str | None = None                             # e.g. "Bank Indonesia"

    def to_dict(self) -> dict[str, Any]:
        # Deferred import to avoid a cycle if schema.py ever grows deps.
        from .schema import SCHEMA_VERSION
        payload = _deep_asdict(self.data)
        prov: dict[str, Any] = {
            "source": self.source,
            "schema_version": SCHEMA_VERSION,
            "retrieved_at": self.retrieved_at,
            "cache_hit": self.cache_hit,
        }
        if self.tier:
            prov["tier"] = self.tier
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
