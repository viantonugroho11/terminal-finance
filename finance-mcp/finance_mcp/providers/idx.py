"""IDX (Bursa Efek Indonesia) provider.

Best-effort adapter over IDX's public web endpoints. Same posture as
`yfinance` scraping — fetched per user request, short-TTL cached,
never redistributed. See ADR-0020.

IDX endpoints sit behind Cloudflare. Plain httpx often works with a
browser-like User-Agent; when it does not, the tool surfaces
`PROVIDER_UNAVAILABLE` and the router falls back to Yahoo. Hardened
`curl_cffi` transport is a follow-up if failure rate warrants it.

Symbols: this adapter accepts either `BBCA` or `BBCA.JK`. Internally
it strips the `.JK` suffix because IDX endpoints want the bare code.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from ..errors import ErrorCode, FinanceError
from ..models import (
    BalanceSheet,
    Board,
    BoardMember,
    BrokerActivity,
    BrokerActivityRow,
    BrokerAggRow,
    BrokerFlowAggregate,
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
    HolderChange,
    HolderChangeList,
    IdxMarketOverview,
    IncomeStatement,
    IndexQuote,
    InsiderTrade,
    InsiderTradeList,
    IpoCalendar,
    IpoEvent,
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

_BASE = "https://www.idx.co.id/primary"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
    "Referer": "https://www.idx.co.id/",
    "X-Requested-With": "XMLHttpRequest",
}


def _bare(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if s.endswith(".JK"):
        s = s[:-3]
    if not s.isalpha() or len(s) != 4:
        raise FinanceError(ErrorCode.INVALID_SYMBOL,
                           f"Not a valid IDX ticker: {symbol!r}",
                           provider="idx", symbol=symbol)
    return s


def _f(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


class IdxProvider:
    """Indonesian equity data straight from IDX."""

    name = "idx"
    tier = "scraped"
    markets = frozenset({"IDX"})
    capabilities = frozenset({
        "quote", "history", "company", "financials", "statements",
        "dividends", "corporate_actions", "sector",
        "foreign_flow", "search", "broker_activity", "order_book",
        "ipo_calendar", "trading_calendar", "disclosures",
        "board", "shareholders", "subsidiaries",
        "idx_market_overview", "idx_market_movers",
        # ADR-0026 flow deep-dive
        "insider_trades", "major_holder_changes", "broker_flow_aggregate",
    })
    requires_api_key = False

    def __init__(self, http: httpx.AsyncClient | None = None,
                 *, timeout: float = 15.0):
        self._owned = http is None
        self._http = http or httpx.AsyncClient(
            headers=_HEADERS, timeout=timeout, follow_redirects=True,
        )

    async def aclose(self) -> None:
        if self._owned:
            await self._http.aclose()

    # ── HTTP helper ────────────────────────────────────────────────

    async def _get_json(self, path: str, params: dict | None = None,
                        *, symbol: str | None = None) -> Any:
        url = f"{_BASE}{path}"
        try:
            r = await self._http.get(url, params=params or {})
        except httpx.TimeoutException as e:
            raise FinanceError(ErrorCode.TIMEOUT, str(e),
                               provider=self.name, symbol=symbol) from e
        except httpx.HTTPError as e:
            raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE, str(e),
                               provider=self.name, symbol=symbol) from e

        if r.status_code == 403 or r.status_code == 503:
            # Cloudflare challenge or block — treat as transient so router
            # can fall through to Yahoo.
            raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE,
                               f"IDX blocked request (HTTP {r.status_code}); "
                               "likely Cloudflare challenge",
                               provider=self.name, symbol=symbol)
        if r.status_code == 404:
            raise FinanceError(ErrorCode.SYMBOL_NOT_FOUND,
                               f"IDX returned 404 for {symbol or path}",
                               provider=self.name, symbol=symbol)
        if r.status_code >= 400:
            raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE,
                               f"IDX HTTP {r.status_code}",
                               provider=self.name, symbol=symbol)
        try:
            return r.json()
        except ValueError as e:
            raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                               f"IDX returned non-JSON: {e}",
                               provider=self.name, symbol=symbol) from e

    # ── MarketDataProvider ─────────────────────────────────────────

    async def quote(self, symbol: str) -> Quote:
        code = _bare(symbol)
        # IDX daily summary carries last trade, previous, volume.
        payload = await self._get_json(
            "/TradingSummary/GetStockSummary",
            params={"code": code, "start": 0, "length": 1},
            symbol=symbol,
        )
        rows = (payload or {}).get("data") or (payload or {}).get("Rows") or []
        if not rows:
            raise FinanceError(ErrorCode.SYMBOL_NOT_FOUND,
                               f"No IDX trading summary for {code}",
                               provider=self.name, symbol=symbol)
        row = rows[0]
        last = _f(row.get("Close") or row.get("Previous"))
        prev = _f(row.get("Previous"))
        vol  = int(_f(row.get("Volume")) or 0)
        if last is None:
            raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                               f"IDX summary missing close for {code}",
                               provider=self.name, symbol=symbol)
        change = (last - prev) if prev else 0.0
        return Quote(
            symbol=f"{code}.JK", price=last, change=change,
            change_percent=(change / prev * 100.0) if prev else 0.0,
            volume=vol, currency="IDR",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    async def history(self, symbol: str, period: str = "6mo",
                      interval: str = "1d") -> list[Candle]:
        code = _bare(symbol)
        payload = await self._get_json(
            "/StockData/GetStockHistory",
            params={"code": code, "period": period},
            symbol=symbol,
        )
        rows = (payload or {}).get("data") or []
        out: list[Candle] = []
        for r in rows:
            try:
                out.append(Candle(
                    date=str(r.get("Date") or r.get("date"))[:10],
                    open=float(r.get("Open") or r.get("OpenPrice") or 0),
                    high=float(r.get("High") or r.get("HighPrice") or 0),
                    low=float(r.get("Low") or r.get("LowPrice") or 0),
                    close=float(r.get("Close") or r.get("ClosePrice") or 0),
                    volume=int(r.get("Volume") or 0),
                ))
            except (TypeError, ValueError):
                continue
        if not out:
            raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                               f"IDX history empty for {code}",
                               provider=self.name, symbol=symbol)
        return out

    async def market_overview(self) -> MarketOverview:
        # IHSG index summary. Kept minimal — this capability isn't in
        # IdxProvider.capabilities, so router won't route here; provided
        # as convenience if a caller ever holds this instance directly.
        raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                           "IDX market_overview not implemented",
                           provider=self.name)

    async def market_movers(self) -> MarketMovers:
        raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                           "IDX market_movers not implemented",
                           provider=self.name)

    # ── FundamentalProvider ────────────────────────────────────────

    async def company(self, symbol: str) -> Company:
        code = _bare(symbol)
        payload = await self._get_json(
            "/ListedCompany/GetCompanyProfilesDetail",
            params={"KodeEmiten": code, "language": "en-us"},
            symbol=symbol,
        )
        rows = (payload or {}).get("Profiles") or (payload or {}).get("data") or []
        prof = rows[0] if isinstance(rows, list) and rows else (payload or {})
        return Company(
            symbol=f"{code}.JK",
            name=prof.get("Name") or prof.get("CompanyName") or code,
            sector=prof.get("Sector") or prof.get("Industry"),
            industry=prof.get("Industry") or prof.get("SubIndustry"),
            country="ID",
            website=prof.get("Website"),
            employees=int(prof.get("Employees") or 0) or None,
            summary=prof.get("BusinessDescription") or prof.get("CompanyProfile"),
            market_cap=_f(prof.get("MarketCap")),
        )

    async def financials(self, symbol: str) -> Financials:
        code = _bare(symbol)
        payload = await self._get_json(
            "/ListedCompany/GetFinancialSummary",
            params={"KodeEmiten": code}, symbol=symbol,
        )
        row = ((payload or {}).get("data") or [{}])[0]
        return Financials(
            symbol=f"{code}.JK",
            pe_ratio=_f(row.get("PER")),
            forward_pe=None,
            peg_ratio=None,
            price_to_book=_f(row.get("PBV")),
            price_to_sales=None,
            profit_margin=_f(row.get("NPM")),
            operating_margin=_f(row.get("OPM")),
            return_on_equity=_f(row.get("ROE")),
            return_on_assets=_f(row.get("ROA")),
            revenue_growth=_f(row.get("RevenueGrowth")),
            earnings_growth=_f(row.get("EarningsGrowth")),
            debt_to_equity=_f(row.get("DER")),
            current_ratio=_f(row.get("CurrentRatio")),
            free_cashflow=_f(row.get("FCF")),
            dividend_yield=_f(row.get("DividendYield")),
            beta=None,
            net_interest_margin=_f(row.get("NIM")),
            non_performing_loan_ratio=_f(row.get("NPL")),
            capital_adequacy_ratio=_f(row.get("CAR")),
            loan_to_deposit_ratio=_f(row.get("LDR")),
            casa_ratio=_f(row.get("CASA")),
            cost_of_credit=_f(row.get("CostOfCredit")),
            loan_growth=_f(row.get("LoanGrowth")),
            deposit_growth=_f(row.get("DepositGrowth")),
        )

    async def financial_statements(self, symbol: str) -> FinancialStatements:
        code = _bare(symbol)
        payload = await self._get_json(
            "/ListedCompany/GetFinancialStatements",
            params={"KodeEmiten": code}, symbol=symbol,
        )
        rows = (payload or {}).get("data") or []
        income, balance, cash = [], [], []
        for r in rows:
            date = str(r.get("Period") or r.get("Date") or "")[:10]
            income.append(IncomeStatement(
                period="annual", date=date,
                revenue=_f(r.get("Revenue")),
                gross_profit=_f(r.get("GrossProfit")),
                operating_income=_f(r.get("OperatingIncome")),
                net_income=_f(r.get("NetIncome")),
                eps=_f(r.get("EPS")),
            ))
            balance.append(BalanceSheet(
                period="annual", date=date,
                total_assets=_f(r.get("TotalAssets")),
                total_liabilities=_f(r.get("TotalLiabilities")),
                total_equity=_f(r.get("TotalEquity")),
                cash=_f(r.get("CashAndEquivalents")),
                total_debt=_f(r.get("TotalDebt")),
            ))
            cash.append(CashFlowStatement(
                period="annual", date=date,
                operating_cash_flow=_f(r.get("OperatingCashFlow")),
                investing_cash_flow=_f(r.get("InvestingCashFlow")),
                financing_cash_flow=_f(r.get("FinancingCashFlow")),
                free_cash_flow=_f(r.get("FreeCashFlow")),
            ))
        return FinancialStatements(
            symbol=f"{code}.JK",
            income=income, balance=balance, cashflow=cash,
        )

    # ── IDX-specific capabilities ──────────────────────────────────

    async def dividends(self, symbol: str) -> DividendHistory:
        code = _bare(symbol)
        payload = await self._get_json(
            "/ListedCompany/GetCorporateActionDividend",
            params={"KodeEmiten": code}, symbol=symbol,
        )
        rows = (payload or {}).get("data") or []
        events: list[DividendEvent] = []
        for r in rows:
            amt = _f(r.get("DividendPerShare") or r.get("Amount"))
            if amt is None:
                continue
            events.append(DividendEvent(
                ex_date=str(r.get("ExDate") or "")[:10],
                payment_date=str(r.get("PaymentDate") or "")[:10] or None,
                amount_per_share=amt,
                currency=str(r.get("Currency") or "IDR"),
            ))
        return DividendHistory(symbol=f"{code}.JK", events=events)

    async def corporate_actions(self, symbol: str) -> CorporateActionHistory:
        code = _bare(symbol)
        payload = await self._get_json(
            "/ListedCompany/GetIssuedHistory",
            params={"KodeEmiten": code}, symbol=symbol,
        )
        rows = (payload or {}).get("data") or []
        events: list[CorporateAction] = []
        for r in rows:
            events.append(CorporateAction(
                date=str(r.get("Date") or r.get("EffectiveDate") or "")[:10],
                kind=str(r.get("Type") or r.get("ActionType") or "other").lower(),
                ratio=(str(r.get("Ratio")) if r.get("Ratio") is not None else None),
                description=r.get("Description"),
            ))
        return CorporateActionHistory(symbol=f"{code}.JK", events=events)

    async def sector(self, symbol: str) -> SectorInfo:
        # Reuse company profile for sector info — IDX-IC lives on the
        # same record.
        code = _bare(symbol)
        payload = await self._get_json(
            "/ListedCompany/GetCompanyProfilesDetail",
            params={"KodeEmiten": code, "language": "en-us"},
            symbol=symbol,
        )
        rows = (payload or {}).get("Profiles") or (payload or {}).get("data") or []
        prof = rows[0] if isinstance(rows, list) and rows else (payload or {})
        return SectorInfo(
            symbol=f"{code}.JK",
            sector_code=prof.get("SectorCode"),
            sector_name=prof.get("Sector"),
            subsector=prof.get("SubSector") or prof.get("Subsector"),
            industry=prof.get("Industry"),
            sub_industry=prof.get("SubIndustry"),
        )

    async def news(self, query: str, limit: int = 10) -> list[NewsItem]:
        raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                           "IDX news not implemented",
                           provider=self.name)

    # ── Microstructure / market-wide capabilities ─────────────────

    async def foreign_flow(self, symbol: str) -> ForeignFlow:
        code = _bare(symbol)
        payload = await self._get_json(
            "/TradingSummary/GetForeignFlow",
            params={"code": code}, symbol=symbol,
        )
        rows = (payload or {}).get("data") or []
        days: list[ForeignFlowDay] = []
        for r in rows:
            buy = _f(r.get("ForeignBuy") or r.get("BuyValue"))
            sell = _f(r.get("ForeignSell") or r.get("SellValue"))
            net = _f(r.get("NetValue"))
            if net is None and buy is not None and sell is not None:
                net = buy - sell
            days.append(ForeignFlowDay(
                date=str(r.get("Date") or "")[:10],
                buy_value=buy, sell_value=sell, net_value=net,
            ))
        return ForeignFlow(symbol=f"{code}.JK", days=days)

    async def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        q = (query or "").strip()
        if not q:
            return []
        payload = await self._get_json(
            "/ListedCompany/GetCompanyProfiles",
            params={"start": 0, "length": max(limit, 20),
                    "keyword": q, "language": "en-us"},
        )
        rows = (payload or {}).get("data") or (payload or {}).get("Rows") or []
        out: list[SearchResult] = []
        for r in rows[:limit]:
            code = str(r.get("KodeEmiten") or r.get("Code") or "").upper()
            if not code:
                continue
            out.append(SearchResult(
                symbol=f"{code}.JK",
                name=str(r.get("NamaEmiten") or r.get("Name") or code),
                sector=r.get("Sektor") or r.get("Sector"),
            ))
        return out

    async def broker_activity(self, symbol: str,
                              date: str | None = None) -> BrokerActivity:
        code = _bare(symbol)
        params: dict[str, Any] = {"code": code}
        if date:
            params["date"] = date
        payload = await self._get_json(
            "/BrokerActivity/GetBrokerSummary",
            params=params, symbol=symbol,
        )
        rows = (payload or {}).get("data") or []
        out: list[BrokerActivityRow] = []
        for r in rows:
            buy_v = _f(r.get("BuyValue"))
            sell_v = _f(r.get("SellValue"))
            net = _f(r.get("NetValue"))
            if net is None and buy_v is not None and sell_v is not None:
                net = buy_v - sell_v
            out.append(BrokerActivityRow(
                broker_code=str(r.get("BrokerCode") or r.get("Broker") or ""),
                broker_name=r.get("BrokerName"),
                buy_lot=int(r.get("BuyLot") or 0) or None,
                sell_lot=int(r.get("SellLot") or 0) or None,
                buy_value=buy_v, sell_value=sell_v, net_value=net,
            ))
        return BrokerActivity(
            symbol=f"{code}.JK",
            date=str((payload or {}).get("date") or date or ""),
            rows=out,
        )

    async def order_book(self, symbol: str, depth: int = 10) -> OrderBook:
        code = _bare(symbol)
        payload = await self._get_json(
            "/MarketData/GetOrderBook",
            params={"code": code, "depth": depth}, symbol=symbol,
        )
        data = payload or {}
        def _levels(rows) -> list[OrderBookLevel]:
            out: list[OrderBookLevel] = []
            for r in (rows or []):
                p = _f(r.get("Price"))
                v = int(r.get("Volume") or 0)
                if p is None or v <= 0:
                    continue
                out.append(OrderBookLevel(
                    price=p, volume=v,
                    orders=int(r.get("Orders") or 0) or None,
                ))
            return out
        return OrderBook(
            symbol=f"{code}.JK",
            timestamp=str(data.get("timestamp")
                          or datetime.now(timezone.utc).isoformat()),
            bids=_levels(data.get("bids")),
            asks=_levels(data.get("asks")),
        )

    async def ipo_calendar(self) -> IpoCalendar:
        payload = await self._get_json(
            "/NewListing/GetNewListing",
            params={"start": 0, "length": 100},
        )
        rows = (payload or {}).get("data") or []
        out: list[IpoEvent] = []
        for r in rows:
            code = str(r.get("Code") or r.get("KodeEmiten") or "").upper()
            if not code:
                continue
            out.append(IpoEvent(
                symbol=f"{code}.JK",
                name=str(r.get("Name") or r.get("NamaEmiten") or code),
                listing_date=str(r.get("ListingDate") or "")[:10],
                offer_price=_f(r.get("OfferPrice")),
                shares_offered=(int(r.get("SharesOffered") or 0) or None),
                sector=r.get("Sector") or r.get("Sektor"),
            ))
        return IpoCalendar(events=out)

    async def trading_calendar(self, year: int) -> TradingCalendar:
        payload = await self._get_json(
            "/TradingCalendar/GetCalendar",
            params={"year": year},
        )
        rows = (payload or {}).get("data") or []
        out: list[TradingCalendarDay] = []
        for r in rows:
            out.append(TradingCalendarDay(
                date=str(r.get("Date") or "")[:10],
                is_trading_day=bool(r.get("IsTradingDay", True)),
                holiday_name=r.get("HolidayName") or r.get("Description"),
            ))
        return TradingCalendar(year=year, days=out)

    async def disclosures(self, symbol: str,
                          limit: int = 20) -> DisclosureFeed:
        code = _bare(symbol)
        payload = await self._get_json(
            "/NewsAnnouncement/GetAnnouncement",
            params={"code": code, "start": 0, "length": limit},
            symbol=symbol,
        )
        rows = (payload or {}).get("data") or []
        out: list[DisclosureItem] = []
        for r in rows[:limit]:
            out.append(DisclosureItem(
                date=str(r.get("Date") or r.get("PublishDate") or "")[:10],
                title=str(r.get("Title") or r.get("Subject") or ""),
                category=r.get("Category"),
                url=r.get("Url") or r.get("Link"),
            ))
        return DisclosureFeed(symbol=f"{code}.JK", items=out)

    async def board(self, symbol: str) -> Board:
        code = _bare(symbol)
        payload = await self._get_json(
            "/ListedCompany/GetBoardOfCommissionerAndDirector",
            params={"KodeEmiten": code, "language": "en-us"},
            symbol=symbol,
        )
        commissioners: list[BoardMember] = []
        directors: list[BoardMember] = []
        for r in (payload or {}).get("Commissioner") or []:
            commissioners.append(BoardMember(
                name=str(r.get("Name") or ""),
                position=str(r.get("Position") or ""),
                since=r.get("Since"),
            ))
        for r in (payload or {}).get("Director") or []:
            directors.append(BoardMember(
                name=str(r.get("Name") or ""),
                position=str(r.get("Position") or ""),
                since=r.get("Since"),
            ))
        return Board(symbol=f"{code}.JK",
                     commissioners=commissioners, directors=directors)

    async def shareholders(self, symbol: str) -> Shareholders:
        code = _bare(symbol)
        payload = await self._get_json(
            "/ListedCompany/GetShareHolder",
            params={"KodeEmiten": code, "language": "en-us"},
            symbol=symbol,
        )
        rows = (payload or {}).get("data") or (payload or {}).get("Shareholders") or []
        out: list[ShareholderEntry] = []
        for r in rows:
            out.append(ShareholderEntry(
                name=str(r.get("Name") or ""),
                kind=r.get("Type") or r.get("Kind"),
                shares=int(r.get("Shares") or 0) or None,
                pct=_f(r.get("Percentage") or r.get("Pct")),
            ))
        return Shareholders(symbol=f"{code}.JK", holders=out)

    async def subsidiaries(self, symbol: str) -> SubsidiaryList:
        code = _bare(symbol)
        payload = await self._get_json(
            "/ListedCompany/GetSubsidiary",
            params={"KodeEmiten": code, "language": "en-us"},
            symbol=symbol,
        )
        rows = (payload or {}).get("data") or []
        out: list[Subsidiary] = []
        for r in rows:
            out.append(Subsidiary(
                name=str(r.get("Name") or r.get("SubsidiaryName") or ""),
                ownership_pct=_f(r.get("Ownership") or r.get("Percentage")),
                business=r.get("Business") or r.get("MainBusiness"),
            ))
        return SubsidiaryList(symbol=f"{code}.JK", subsidiaries=out)

    async def idx_market_overview(self) -> IdxMarketOverview:
        idx_payload = await self._get_json(
            "/StockData/GetIndexData",
            params={"code": "COMPOSITE"},
        )
        indices: list[IndexQuote] = []
        for r in ((idx_payload or {}).get("data") or []):
            val = _f(r.get("Value") or r.get("Last"))
            if val is None:
                continue
            prev = _f(r.get("Previous")) or 0.0
            change = val - prev
            indices.append(IndexQuote(
                code=str(r.get("Code") or ""),
                value=val, change=change,
                change_percent=(change / prev * 100.0) if prev else 0.0,
                volume=int(r.get("Volume") or 0) or None,
                value_traded=_f(r.get("ValueTraded")),
                timestamp=str(r.get("Timestamp")
                              or datetime.now(timezone.utc).isoformat()),
            ))

        sec_payload = await self._get_json(
            "/StockData/GetSectoralSummary",
            params={},
        )
        sectors: list[SectorPerf] = []
        for r in ((sec_payload or {}).get("data") or []):
            chg = _f(r.get("ChangePct") or r.get("ChangePercent"))
            if chg is None:
                continue
            sectors.append(SectorPerf(
                sector_code=str(r.get("Code") or ""),
                sector_name=str(r.get("Name") or r.get("Sector") or ""),
                change_percent=chg,
                value_traded=_f(r.get("ValueTraded")),
            ))
        return IdxMarketOverview(indices=indices, sectors=sectors)

    async def idx_market_movers(self) -> MarketMovers:
        async def _fetch(kind: str) -> list[MoverItem]:
            payload = await self._get_json(
                "/StockData/GetTopMovers",
                params={"type": kind, "length": 10},
            )
            out: list[MoverItem] = []
            for r in ((payload or {}).get("data") or []):
                price = _f(r.get("Close") or r.get("Price"))
                prev = _f(r.get("Previous")) or 0.0
                if price is None:
                    continue
                change = price - prev
                out.append(MoverItem(
                    symbol=f"{str(r.get('Code') or '').upper()}.JK",
                    name=r.get("Name"),
                    price=price, change=change,
                    change_percent=(change / prev * 100.0) if prev else 0.0,
                    volume=int(r.get("Volume") or 0),
                ))
            return out

        gainers = await _fetch("gainer")
        losers  = await _fetch("loser")
        active  = await _fetch("active")
        return MarketMovers(top_gainers=gainers, top_losers=losers,
                            most_active=active)

    # ── ADR-0026: flow deep-dive ────────────────────────────────────

    async def insider_trades(self, symbol: str, days: int = 30) -> InsiderTradeList:
        """Insider transactions (director/commissioner) via IDX disclosures.

        IDX publishes these under the AnnouncementStock endpoint tagged
        `TransaksiSaham`. Payload shape is best-effort — always tolerate
        missing fields; skip rows that cannot be parsed.
        """
        code = _bare(symbol)
        payload = await self._get_json(
            "/ListedCompany/GetInsiderTrades",
            params={"code": code, "period": days},
            symbol=symbol,
        )
        rows = (payload or {}).get("data") or (payload or {}).get("Rows") or []
        trades: list[InsiderTrade] = []
        for r in rows:
            try:
                trades.append(InsiderTrade(
                    symbol=f"{code}.JK",
                    date=str(r.get("Date") or r.get("TransDate") or ""),
                    name=str(r.get("Name") or ""),
                    role=r.get("Role") or r.get("Position"),
                    side=str(r.get("Side") or r.get("Type") or "").upper(),
                    qty=int(r.get("Quantity") or r.get("Qty") or 0),
                    price=_f(r.get("Price")),
                    total_value=_f(r.get("TotalValue") or r.get("Value")),
                    source_url=r.get("Url"),
                ))
            except (TypeError, ValueError):
                continue
        return InsiderTradeList(symbol=f"{code}.JK", days=days, trades=trades)

    async def major_holder_changes(self, symbol: str,
                                   days: int = 30) -> HolderChangeList:
        code = _bare(symbol)
        payload = await self._get_json(
            "/ListedCompany/GetMajorHolderChanges",
            params={"code": code, "period": days},
            symbol=symbol,
        )
        rows = (payload or {}).get("data") or []
        changes: list[HolderChange] = []
        for r in rows:
            try:
                before = _f(r.get("PctBefore"))
                after = _f(r.get("PctAfter"))
                delta = _f(r.get("Change"))
                if delta is None and before is not None and after is not None:
                    delta = after - before
                changes.append(HolderChange(
                    symbol=f"{code}.JK",
                    date=str(r.get("Date") or ""),
                    holder_name=str(r.get("Holder") or r.get("Name") or ""),
                    pct_before=before,
                    pct_after=after,
                    change_pct=delta,
                    source_url=r.get("Url"),
                ))
            except (TypeError, ValueError):
                continue
        return HolderChangeList(symbol=f"{code}.JK", days=days,
                                changes=changes)

    async def broker_flow_agg(self, symbol: str,
                              days: int = 5) -> BrokerFlowAggregate:
        """Rank net buyers / sellers from broker activity.

        KNOWN LIMITATION — `days` is accepted but not yet honoured. The
        upstream broker-summary endpoint exposes no historical-date
        parameter, so only the latest session is available; requesting
        `days=5` returns a single day and reports `days=1` in the reply.
        Re-fetching would return identical data, so we fetch once.

        Multi-day aggregation needs either a dated upstream endpoint or a
        local daily snapshot table. The accumulator below is already
        shaped for it: when a per-date source exists, loop the fetch and
        the totals / `days_active` counters work unchanged.
        """
        totals: dict[str, dict[str, Any]] = {}
        active_days = 0
        try:
            per_day = await self.broker_activity(symbol, date=None)
        except FinanceError:
            per_day = None
        if per_day is not None and per_day.rows:
            active_days = 1
            for row in per_day.rows:
                acc = totals.setdefault(row.broker_code, {
                    "name": row.broker_name,
                    "buy": 0.0, "sell": 0.0, "net": 0.0, "days": 0,
                })
                acc["buy"]  += float(row.buy_value or 0.0)
                acc["sell"] += float(row.sell_value or 0.0)
                acc["net"]  += float(row.net_value or 0.0)
                acc["days"] += 1
        aggregated = [
            BrokerAggRow(
                broker_code=code, broker_name=v["name"],
                net_value=v["net"], buy_value=v["buy"],
                sell_value=v["sell"], days_active=v["days"],
            )
            for code, v in totals.items()
        ]
        aggregated.sort(key=lambda r: r.net_value, reverse=True)
        top_buyers = aggregated[:10]
        top_sellers = sorted(aggregated, key=lambda r: r.net_value)[:10]
        return BrokerFlowAggregate(
            symbol=f"{_bare(symbol)}.JK", days=max(active_days, 1),
            top_net_buyers=top_buyers, top_net_sellers=top_sellers,
        )
