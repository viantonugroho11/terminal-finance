"""Bank Indonesia macro provider.

Covers `bi_rate` (BI 7-Day Reverse Repo Rate → BI-Rate) and `jisdor`
(USD/IDR reference rate). BI publishes these on public pages; no
public REST API. This adapter hits their internal JSON endpoints used
by the public site's own JS. When BI changes those endpoints (they do
occasionally), the adapter degrades to `DATA_UNAVAILABLE` and the
router surfaces that to the skill without inventing numbers.

See ADR-0020. Attribution: "Bank Indonesia".
"""
from __future__ import annotations
from typing import Any

import httpx

from ..errors import FinanceError, ErrorCode
from ..models import MacroObservation, MacroSeries


_BASE = "https://www.bi.go.id"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
    "Referer": "https://www.bi.go.id/",
}


def _f(v: Any) -> float | None:
    try:
        if v in (None, ""):
            return None
        s = str(v).replace(",", ".").replace("%", "").strip()
        f = float(s)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


class BiProvider:
    """Bank Indonesia macro adapter."""

    name = "bi"
    tier = "primary"
    markets = frozenset({"MACRO"})
    capabilities = frozenset({
        "macro:bi_rate", "macro:jisdor",
    })
    requires_api_key = False
    attribution = "Bank Indonesia"

    def __init__(self, http: httpx.AsyncClient | None = None,
                 *, timeout: float = 15.0):
        self._owned = http is None
        self._http = http or httpx.AsyncClient(
            headers=_HEADERS, timeout=timeout, follow_redirects=True,
        )

    async def aclose(self) -> None:
        if self._owned:
            await self._http.aclose()

    async def _get_json(self, path: str, params: dict | None = None) -> Any:
        try:
            r = await self._http.get(f"{_BASE}{path}", params=params or {})
        except httpx.TimeoutException as e:
            raise FinanceError(ErrorCode.TIMEOUT, str(e), provider=self.name) from e
        except httpx.HTTPError as e:
            raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE, str(e),
                               provider=self.name) from e
        if r.status_code in (403, 503):
            raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE,
                               f"BI blocked (HTTP {r.status_code})",
                               provider=self.name)
        if r.status_code >= 400:
            raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE,
                               f"BI HTTP {r.status_code}", provider=self.name)
        try:
            return r.json()
        except ValueError as e:
            raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                               f"BI non-JSON: {e}", provider=self.name) from e

    async def macro_indicator(self, indicator: str) -> MacroSeries:
        ind = indicator.lower()
        if ind == "bi_rate":
            return await self._bi_rate()
        if ind in ("jisdor", "fx_usd_idr"):
            return await self._jisdor()
        raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                           f"BI does not serve indicator {indicator!r}",
                           provider=self.name)

    async def _bi_rate(self) -> MacroSeries:
        # BI publishes the rate history JSON behind the indicator page.
        payload = await self._get_json("/biwebservice/api/getBIRateHistory")
        rows = (payload or {}).get("data") or []
        obs: list[MacroObservation] = []
        for r in rows:
            val = _f(r.get("Rate") or r.get("rate") or r.get("value"))
            if val is None:
                continue
            obs.append(MacroObservation(
                period=str(r.get("EffectiveDate") or r.get("date") or "")[:10],
                value=val, unit="%",
            ))
        if not obs:
            raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                               "BI rate history empty",
                               provider=self.name)
        return MacroSeries(
            indicator="bi_rate", source=self.name, unit="%",
            observations=obs, frequency="monthly",
            description="BI 7-Day Reverse Repo Rate (BI-Rate)",
            attribution=self.attribution,
        )

    async def _jisdor(self) -> MacroSeries:
        payload = await self._get_json(
            "/biwebservice/api/getJisdorHistory",
            params={"currency": "USD"},
        )
        rows = (payload or {}).get("data") or []
        obs: list[MacroObservation] = []
        for r in rows:
            val = _f(r.get("Kurs") or r.get("Rate") or r.get("value"))
            if val is None:
                continue
            obs.append(MacroObservation(
                period=str(r.get("Date") or r.get("date") or "")[:10],
                value=val, unit="IDR/USD",
            ))
        if not obs:
            raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                               "JISDOR history empty",
                               provider=self.name)
        return MacroSeries(
            indicator="jisdor", source=self.name, unit="IDR/USD",
            observations=obs, frequency="daily",
            description="Jakarta Interbank Spot Dollar Rate (USD/IDR)",
            attribution=self.attribution,
        )
