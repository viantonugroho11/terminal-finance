"""KSEI provider — ownership breakdown (ADR-0026).

KSEI (Kustodian Sentral Efek Indonesia) publishes a monthly Holding
Composition report. There is no public JSON API; the operational
pipeline scrapes the CSV/HTML export.

This provider parses whichever payload it is handed (CSV rows or a
pre-parsed dict) so the ingest scheduler can pick the freshest export
and the caller keeps a stable interface. HTTP fetch is intentionally
kept simple — same posture as `IdxProvider`; if KSEI blocks or shape
changes, `PROVIDER_UNAVAILABLE` bubbles up and the router does not
substitute a wrong number.
"""
from __future__ import annotations
import csv
import io
from datetime import datetime, timezone
from typing import Any

import httpx

from ..errors import FinanceError, ErrorCode
from ..models import OwnershipBreakdown


_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _UA, "Accept": "text/csv, text/html, */*"}

_BASE = "https://www.ksei.co.id/services/holding-composition"


def _to_pct(v: Any) -> float | None:
    if v is None:
        return None
    try:
        s = str(v).strip().rstrip("%").replace(",", ".")
        return float(s)
    except ValueError:
        return None


def _to_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(str(v).replace(",", "").replace(".", ""))
    except ValueError:
        return None


def parse_csv(text: str, symbol: str) -> OwnershipBreakdown | None:
    """Parse a KSEI ownership CSV; return None if symbol not found."""
    sym = symbol.upper().split(".")[0]
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        code = str(row.get("Code") or row.get("code") or "").upper()
        if code != sym:
            continue
        return OwnershipBreakdown(
            symbol=f"{sym}.JK",
            as_of=str(row.get("AsOf") or row.get("Date")
                      or datetime.now(timezone.utc).date().isoformat()),
            foreign_pct=_to_pct(row.get("ForeignPct") or row.get("Foreign")),
            domestic_pct=_to_pct(row.get("DomesticPct") or row.get("Domestic")),
            local_institutional_pct=_to_pct(
                row.get("LocalInstitutionalPct") or row.get("Institutional")
            ),
            retail_pct=_to_pct(row.get("RetailPct") or row.get("Retail")),
            total_shares=_to_int(row.get("TotalShares")),
        )
    return None


class KseiProvider:
    """Ownership breakdown provider — one capability, IDX market only."""

    name = "ksei"
    tier = "primary"
    markets = frozenset({"IDX"})
    capabilities = frozenset({"ownership_breakdown"})
    requires_api_key = False

    def __init__(self, http: httpx.AsyncClient | None = None,
                 *, timeout: float = 15.0,
                 fetcher: Any = None):
        """`fetcher` is injectable for tests: an async fn (symbol) -> str."""
        self._owned = http is None
        self._http = http or httpx.AsyncClient(
            headers=_HEADERS, timeout=timeout, follow_redirects=True,
        )
        self._fetcher = fetcher

    async def aclose(self) -> None:
        if self._owned:
            await self._http.aclose()

    async def _fetch_csv(self, symbol: str) -> str:
        if self._fetcher is not None:
            return await self._fetcher(symbol)
        url = f"{_BASE}?code={symbol.upper().split('.')[0]}&format=csv"
        try:
            r = await self._http.get(url)
        except httpx.HTTPError as e:
            raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE,
                               f"KSEI fetch failed: {e}",
                               provider=self.name, symbol=symbol) from e
        if r.status_code >= 400:
            raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE,
                               f"KSEI HTTP {r.status_code}",
                               provider=self.name, symbol=symbol)
        return r.text

    async def ownership_breakdown(self, symbol: str) -> OwnershipBreakdown:
        text = await self._fetch_csv(symbol)
        parsed = parse_csv(text, symbol)
        if parsed is None:
            raise FinanceError(
                ErrorCode.DATA_UNAVAILABLE,
                f"KSEI has no ownership row for {symbol}",
                provider=self.name, symbol=symbol,
            )
        return parsed
