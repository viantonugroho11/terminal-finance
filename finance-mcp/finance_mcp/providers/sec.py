"""SEC EDGAR primary-source provider (US filings + XBRL facts).

Covers:
  - Filings history per company (10-K, 10-Q, 8-K, Form 4, 13F-HR, …)
  - Structured company facts from XBRL (Revenues, NetIncomeLoss, …)

SEC endpoints:
  - https://www.sec.gov/files/company_tickers.json     — ticker → CIK map
  - https://data.sec.gov/submissions/CIK{padded}.json  — filing history
  - https://data.sec.gov/api/xbrl/companyfacts/CIK{padded}.json — facts

SEC policy: every request MUST send a User-Agent identifying the caller
(name + email). Missing UA → 403. We read this from FINANCE_SEC_USER_AGENT.
Rate limit: 10 req/sec (SEC will 429 above that). Retry handled by
`retry.with_retry` because 429/timeout map to retryable codes.

See ADR-0018.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from ..errors import ErrorCode, FinanceError
from ..models import (
    SecFactObservation,
    SecFactSeries,
    SecFiling,
    SecFilings,
)

_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
_FACTS_BASE       = "https://data.sec.gov/api/xbrl/companyfacts"
_TICKERS_URL      = "https://www.sec.gov/files/company_tickers.json"


def _default_ua() -> str:
    ua = os.getenv("FINANCE_SEC_USER_AGENT", "").strip()
    if not ua:
        # SEC policy requires identifying UA; keep a clear placeholder
        # so misconfig is obvious in error messages, not a stealth 403.
        return "finance-mcp (contact-unset - set FINANCE_SEC_USER_AGENT)"
    return ua


def _pad_cik(cik: int | str) -> str:
    return str(int(str(cik).lstrip("0") or "0")).zfill(10)


def _n(v: Any) -> float | None:
    try:
        if v in (None, ""):
            return None
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


class SecProvider:
    """SEC EDGAR primary source. Requires FINANCE_SEC_USER_AGENT."""

    name = "sec"
    tier = "primary"
    markets = frozenset({"US"})
    capabilities = frozenset({"sec:filings", "sec:facts"})
    requires_api_key = False   # no key, but UA is mandatory
    attribution = "U.S. Securities and Exchange Commission (EDGAR)"

    def __init__(self,
                 http: httpx.AsyncClient | None = None,
                 *, timeout: float = 20.0,
                 ticker_map: dict[str, int] | None = None):
        ua = _default_ua()
        headers = {
            "User-Agent": ua,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        }
        self._owned = http is None
        self._http = http or httpx.AsyncClient(
            headers=headers, timeout=timeout, follow_redirects=True,
        )
        self._ticker_map: dict[str, int] | None = ticker_map

    async def aclose(self) -> None:
        if self._owned:
            await self._http.aclose()

    # ── HTTP helpers ───────────────────────────────────────────────

    async def _get_json(self, url: str, *, symbol: str | None = None) -> Any:
        try:
            r = await self._http.get(url)
        except httpx.TimeoutException as e:
            raise FinanceError(ErrorCode.TIMEOUT, str(e),
                               provider=self.name, symbol=symbol) from e
        except httpx.HTTPError as e:
            raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE, str(e),
                               provider=self.name, symbol=symbol) from e
        if r.status_code == 403:
            raise FinanceError(ErrorCode.AUTHENTICATION_FAILED,
                               "SEC rejected request — set FINANCE_SEC_USER_AGENT "
                               "to 'Name email@example.com'",
                               provider=self.name, symbol=symbol)
        if r.status_code == 404:
            raise FinanceError(ErrorCode.SYMBOL_NOT_FOUND,
                               f"SEC 404 for {url}", provider=self.name,
                               symbol=symbol)
        if r.status_code == 429:
            raise FinanceError(ErrorCode.RATE_LIMITED,
                               "SEC rate-limited (10 req/sec cap)",
                               provider=self.name, symbol=symbol,
                               retry_after_seconds=1)
        if r.status_code >= 400:
            raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE,
                               f"SEC HTTP {r.status_code}",
                               provider=self.name, symbol=symbol)
        try:
            return r.json()
        except ValueError as e:
            raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                               f"SEC non-JSON: {e}",
                               provider=self.name, symbol=symbol) from e

    # ── Ticker → CIK ───────────────────────────────────────────────

    async def _load_ticker_map(self) -> dict[str, int]:
        if self._ticker_map is not None:
            return self._ticker_map
        payload = await self._get_json(_TICKERS_URL)
        # Shape: { "0": {"cik_str": 320193, "ticker": "AAPL", "title": "..."} , ... }
        out: dict[str, int] = {}
        for entry in (payload or {}).values() if isinstance(payload, dict) else []:
            t = str(entry.get("ticker", "")).upper()
            cik = entry.get("cik_str")
            if t and cik is not None:
                out[t] = int(cik)
        self._ticker_map = out
        return out

    async def _resolve_cik(self, symbol: str) -> int:
        s = (symbol or "").strip().upper()
        if not s:
            raise FinanceError(ErrorCode.INVALID_SYMBOL,
                               "empty symbol", provider=self.name)
        m = await self._load_ticker_map()
        cik = m.get(s)
        if cik is None:
            raise FinanceError(ErrorCode.SYMBOL_NOT_FOUND,
                               f"SEC has no CIK for ticker {s!r}",
                               provider=self.name, symbol=symbol)
        return int(cik)

    # ── Filings ────────────────────────────────────────────────────

    async def sec_filings(self, symbol: str, form_type: str | None = None,
                          limit: int = 20) -> SecFilings:
        cik = await self._resolve_cik(symbol)
        padded = _pad_cik(cik)
        url = f"{_SUBMISSIONS_BASE}/CIK{padded}.json"
        payload = await self._get_json(url, symbol=symbol)
        recent = ((payload or {}).get("filings") or {}).get("recent") or {}

        # SEC packs recent filings as parallel arrays.
        accs   = recent.get("accessionNumber") or []
        forms  = recent.get("form") or []
        filed  = recent.get("filingDate") or []
        report = recent.get("reportDate") or []
        docs   = recent.get("primaryDocument") or []

        items: list[SecFiling] = []
        for i, form in enumerate(forms):
            if form_type and form != form_type:
                continue
            acc = accs[i] if i < len(accs) else ""
            fd = filed[i] if i < len(filed) else ""
            rd = report[i] if i < len(report) else None
            doc = docs[i] if i < len(docs) else None
            url_i = None
            if acc and doc:
                acc_nodash = acc.replace("-", "")
                url_i = (f"https://www.sec.gov/Archives/edgar/data/"
                         f"{int(cik)}/{acc_nodash}/{doc}")
            items.append(SecFiling(
                accession_no=acc, form=form,
                filed_date=fd, report_date=rd,
                primary_document=doc, url=url_i,
            ))
            if len(items) >= limit:
                break

        return SecFilings(
            symbol=symbol.upper(), cik=padded,
            entity_name=(payload or {}).get("name"),
            items=items,
        )

    # ── Company facts (XBRL) ───────────────────────────────────────

    async def sec_facts(self, symbol: str, concept: str,
                        taxonomy: str = "us-gaap") -> SecFactSeries:
        cik = await self._resolve_cik(symbol)
        padded = _pad_cik(cik)
        url = f"{_FACTS_BASE}/CIK{padded}.json"
        payload = await self._get_json(url, symbol=symbol)

        facts = ((payload or {}).get("facts") or {}).get(taxonomy) or {}
        node = facts.get(concept)
        if node is None:
            raise FinanceError(
                ErrorCode.DATA_UNAVAILABLE,
                f"SEC has no {taxonomy}:{concept} for CIK {padded}. "
                f"Try a different concept (e.g. Revenues, NetIncomeLoss).",
                provider=self.name, symbol=symbol,
            )

        units = node.get("units") or {}
        # Prefer USD / USD/shares; fall back to whatever the concept uses.
        preferred = ("USD", "USD/shares", "shares", "pure")
        unit_key = next((u for u in preferred if u in units),
                        next(iter(units), None))
        if unit_key is None:
            raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                               f"SEC concept {concept} has no unit series",
                               provider=self.name, symbol=symbol)

        obs: list[SecFactObservation] = []
        for row in units.get(unit_key, []):
            v = _n(row.get("val"))
            if v is None:
                continue
            obs.append(SecFactObservation(
                value=v, unit=unit_key,
                period_end=str(row.get("end", "")),
                period_start=(str(row.get("start")) if row.get("start") else None),
                form=row.get("form"),
                filed_date=row.get("filed"),
                accession_no=row.get("accn"),
            ))
        obs.sort(key=lambda o: o.period_end)

        return SecFactSeries(
            symbol=symbol.upper(), cik=padded,
            concept=concept, taxonomy=taxonomy,
            label=node.get("label"),
            description=node.get("description"),
            observations=obs,
        )
