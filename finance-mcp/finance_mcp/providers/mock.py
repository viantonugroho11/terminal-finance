"""Deterministic mock provider — tests never touch the network.

Prices are seeded from a hash of the symbol so tests are stable across runs.
Set FINANCE_PROVIDER=mock to run the whole MCP against fake data.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from ..models import (
    BalanceSheet,
    Board,
    BoardMember,
    BrokerActivity,
    BrokerActivityRow,
    Candle,
    CashFlowStatement,
    Company,
    CorporateAction,
    CorporateActionHistory,
    DisclosureFeed,
    DisclosureItem,
    DividendEvent,
    DividendHistory,
    Financials,
    FinancialStatements,
    ForeignFlow,
    ForeignFlowDay,
    IdxMarketOverview,
    IncomeStatement,
    IndexQuote,
    IpoCalendar,
    IpoEvent,
    MacroObservation,
    MacroSeries,
    MarketMovers,
    MarketOverview,
    MoverItem,
    NewsItem,
    OrderBook,
    OrderBookLevel,
    Quote,
    SearchResult,
    SectorInfo,
    SectorPerf,
    ShareholderEntry,
    Shareholders,
    Subsidiary,
    SubsidiaryList,
    TradingCalendar,
    TradingCalendarDay,
)


def _seed(symbol: str) -> float:
    h = hashlib.sha256(symbol.upper().encode()).hexdigest()
    return (int(h[:8], 16) % 90_000) / 100.0 + 10.0  # 10.00 .. 909.99


class MockProvider:
    name = "mock"
    tier = "mock"
    markets = frozenset({"US", "GLOBAL", "IDX", "CRYPTO", "MACRO"})
    capabilities = frozenset({
        "quote", "history", "company", "financials", "statements",
        "news", "market_overview", "market_movers",
        "dividends", "corporate_actions", "sector",
        "macro:bi_rate", "macro:jisdor", "macro:inflation",
        "macro:gdp", "macro:cpi", "macro:unemployment",
        "macro:banking_spi",
        "foreign_flow", "search", "broker_activity", "order_book",
        "ipo_calendar", "trading_calendar", "disclosures",
        "board", "shareholders", "subsidiaries",
        "idx_market_overview", "idx_market_movers",
        "sec:filings", "sec:facts",
    })
    requires_api_key = False

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

    async def dividends(self, symbol: str) -> DividendHistory:
        s = _seed(symbol)
        return DividendHistory(
            symbol=symbol.upper(),
            events=[
                DividendEvent(ex_date=f"{y}-06-15", payment_date=f"{y}-07-15",
                              amount_per_share=round(s * 0.005, 2), currency="USD")
                for y in (2023, 2024, 2025)
            ],
        )

    async def corporate_actions(self, symbol: str) -> CorporateActionHistory:
        return CorporateActionHistory(
            symbol=symbol.upper(),
            events=[
                CorporateAction(date="2024-08-01", kind="split",
                                ratio="2:1", description="Mock 2-for-1 split"),
            ],
        )

    async def sec_filings(self, symbol: str, form_type: str | None = None,
                          limit: int = 20):
        from ..models import SecFiling, SecFilings
        forms = [f for f in ("10-K", "10-Q", "8-K", "4")
                 if (not form_type or f == form_type)]
        return SecFilings(
            symbol=symbol.upper(), cik="0000000000",
            entity_name=f"{symbol.upper()} Inc.",
            items=[SecFiling(
                accession_no=f"0001-{i:04d}", form=f,
                filed_date=f"2025-0{i+1}-15", report_date=f"2025-0{i+1}-01",
                primary_document="filing.htm",
                url=f"https://example.com/edgar/{f}",
            ) for i, f in enumerate(forms[:limit])],
        )

    async def sec_facts(self, symbol: str, concept: str,
                        taxonomy: str = "us-gaap"):
        from ..models import SecFactObservation, SecFactSeries
        return SecFactSeries(
            symbol=symbol.upper(), cik="0000000000",
            concept=concept, taxonomy=taxonomy,
            label=f"Mock {concept}",
            description=f"Mock XBRL series for {concept}",
            observations=[
                SecFactObservation(value=100.0 + i, unit="USD",
                                   period_end=f"2024-0{i+1}-30",
                                   period_start=f"2024-0{i}-01" if i else None,
                                   form="10-Q",
                                   filed_date=f"2024-0{i+2}-15",
                                   accession_no=f"0002-{i:04d}")
                for i in range(3)
            ],
        )

    async def foreign_flow(self, symbol: str) -> ForeignFlow:
        s = _seed(symbol)
        return ForeignFlow(
            symbol=symbol.upper(),
            days=[
                ForeignFlowDay(date=f"2025-08-{d:02d}",
                               buy_value=s * 1e6, sell_value=s * 0.9e6,
                               net_value=s * 0.1e6)
                for d in (11, 12, 13)
            ],
        )

    async def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        q = (query or "").strip().upper()
        return [SearchResult(symbol=f"{q}.JK", name=f"{q} Tbk",
                             sector="Technology")] if q else []

    async def broker_activity(self, symbol: str,
                              date: str | None = None) -> BrokerActivity:
        return BrokerActivity(
            symbol=symbol.upper(), date=date or "2025-08-13",
            rows=[
                BrokerActivityRow(broker_code="YP", broker_name="MockSec",
                                  buy_lot=1000, sell_lot=800,
                                  buy_value=1e9, sell_value=8e8, net_value=2e8),
                BrokerActivityRow(broker_code="CC", broker_name="MockBroker",
                                  buy_lot=500, sell_lot=700,
                                  buy_value=5e8, sell_value=7e8, net_value=-2e8),
            ],
        )

    async def order_book(self, symbol: str, depth: int = 10) -> OrderBook:
        s = _seed(symbol)
        return OrderBook(
            symbol=symbol.upper(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            bids=[OrderBookLevel(price=s - i, volume=1000 * (i + 1))
                  for i in range(min(depth, 5))],
            asks=[OrderBookLevel(price=s + 1 + i, volume=1000 * (i + 1))
                  for i in range(min(depth, 5))],
        )

    async def ipo_calendar(self) -> IpoCalendar:
        return IpoCalendar(events=[
            IpoEvent(symbol="MOCK.JK", name="Mock Tbk",
                     listing_date="2025-09-01", offer_price=100.0,
                     shares_offered=1_000_000, sector="Technology"),
        ])

    async def trading_calendar(self, year: int) -> TradingCalendar:
        return TradingCalendar(year=year, days=[
            TradingCalendarDay(date=f"{year}-01-01",
                               is_trading_day=False,
                               holiday_name="New Year"),
            TradingCalendarDay(date=f"{year}-01-02", is_trading_day=True),
        ])

    async def disclosures(self, symbol: str, limit: int = 20) -> DisclosureFeed:
        return DisclosureFeed(symbol=symbol.upper(), items=[
            DisclosureItem(date="2025-08-10",
                           title=f"Mock disclosure for {symbol.upper()}",
                           category="Financial Report",
                           url="https://example.com/mock"),
        ])

    async def board(self, symbol: str) -> Board:
        return Board(
            symbol=symbol.upper(),
            commissioners=[BoardMember(name="Mock Komisaris",
                                       position="President Commissioner",
                                       since="2020")],
            directors=[BoardMember(name="Mock Direktur",
                                   position="President Director",
                                   since="2021")],
        )

    async def shareholders(self, symbol: str) -> Shareholders:
        return Shareholders(symbol=symbol.upper(), holders=[
            ShareholderEntry(name="Public", kind="institution",
                             shares=500_000_000, pct=50.0),
            ShareholderEntry(name="Founder", kind="individual",
                             shares=500_000_000, pct=50.0),
        ])

    async def subsidiaries(self, symbol: str) -> SubsidiaryList:
        return SubsidiaryList(symbol=symbol.upper(), subsidiaries=[
            Subsidiary(name="Mock Subsidiary A", ownership_pct=99.9,
                       business="Software"),
        ])

    async def idx_market_overview(self) -> IdxMarketOverview:
        now = datetime.now(timezone.utc).isoformat()
        return IdxMarketOverview(
            indices=[
                IndexQuote(code="IHSG", value=7500.0, change=25.0,
                           change_percent=0.33, volume=15_000_000_000,
                           value_traded=1.2e13, timestamp=now),
                IndexQuote(code="LQ45", value=1000.0, change=3.0,
                           change_percent=0.30, volume=5_000_000_000,
                           value_traded=6e12, timestamp=now),
            ],
            sectors=[
                SectorPerf(sector_code="A", sector_name="Financials",
                           change_percent=0.85, value_traded=4e12),
                SectorPerf(sector_code="G", sector_name="Technology",
                           change_percent=-0.40, value_traded=8e11),
            ],
        )

    async def idx_market_movers(self) -> MarketMovers:
        def _mv(sym, pct):
            price = _seed(sym); change = price * pct / 100
            return MoverItem(symbol=f"{sym}.JK", name=f"{sym} Tbk",
                             price=price, change=change,
                             change_percent=pct, volume=5_000_000)
        return MarketMovers(
            top_gainers=[_mv("AAAA", 24.9), _mv("BBBB", 22.1)],
            top_losers=[_mv("YYYY", -12.5), _mv("ZZZZ", -10.0)],
            most_active=[_mv("BBCA", 0.5), _mv("BBRI", -0.2)],
        )

    async def macro_indicator(self, indicator: str) -> MacroSeries:
        units = {
            "bi_rate": "%", "jisdor": "IDR/USD", "inflation": "%",
            "gdp": "%", "cpi": "index", "unemployment": "%",
            "banking_spi": "%",
        }
        u = units.get(indicator.lower(), "%")
        return MacroSeries(
            indicator=indicator, source="mock", unit=u,
            observations=[
                MacroObservation(period="2025-06", value=6.00, unit=u),
                MacroObservation(period="2025-07", value=6.00, unit=u),
                MacroObservation(period="2025-08", value=5.75, unit=u),
            ],
            frequency="monthly",
            description=f"Mock series for {indicator}",
            attribution="mock",
        )

    async def sector(self, symbol: str) -> SectorInfo:
        return SectorInfo(
            symbol=symbol.upper(), sector_code="A1", sector_name="Technology",
            subsector="Software", industry="Application Software",
            sub_industry="Enterprise SaaS",
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
