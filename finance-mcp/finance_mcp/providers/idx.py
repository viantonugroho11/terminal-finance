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
import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from ..errors import FinanceError, ErrorCode, classify
from ..models import (
    Quote, Candle, Company, Financials,
    IncomeStatement, BalanceSheet, CashFlowStatement, FinancialStatements,
    NewsItem, MarketOverview, MarketMovers,
    DividendEvent, DividendHistory,
    CorporateAction, CorporateActionHistory,
    SectorInfo,
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
