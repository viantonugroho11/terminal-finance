"""BPS (Badan Pusat Statistik) macro provider.

Uses BPS WebAPI (https://webapi.bps.go.id/). Requires a free developer
key set as `FINANCE_BPS_API_KEY`. Without the key the provider fails
`AUTHENTICATION_FAILED` on any call and the router treats that as a
stop-code (no lower-tier fallback attempts).

Covers `gdp`, `cpi`/`inflation`, `unemployment`. BPS uses numeric
variable IDs — the map below tracks them.

Attribution: "Badan Pusat Statistik".
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from ..errors import ErrorCode, FinanceError
from ..models import MacroObservation, MacroSeries

_BASE = "https://webapi.bps.go.id/v1/api"
_UA = "finance-mcp/0.1"
_HEADERS = {"User-Agent": _UA, "Accept": "application/json"}

# BPS var IDs (subject to revision — verify against your API console).
# Domain "0000" = nasional.
_VAR: dict[str, tuple[str, str, str, str]] = {
    # indicator: (bps_var_id, unit, frequency, human description)
    "gdp":          ("104", "%",  "quarterly", "PDB — pertumbuhan tahunan"),
    "cpi":          ("907", "index", "monthly", "IHK (Consumer Price Index)"),
    "inflation":    ("1905", "%", "monthly", "Inflasi YoY"),
    "unemployment": ("543",  "%", "quarterly", "Tingkat Pengangguran Terbuka"),
}


class BpsProvider:
    """BPS macro adapter — requires FINANCE_BPS_API_KEY."""

    name = "bps"
    tier = "primary"
    markets = frozenset({"MACRO"})
    capabilities = frozenset({
        "macro:gdp", "macro:cpi", "macro:inflation", "macro:unemployment",
    })
    requires_api_key = True
    attribution = "Badan Pusat Statistik (BPS)"

    def __init__(self, http: httpx.AsyncClient | None = None,
                 *, timeout: float = 15.0, api_key: str | None = None):
        self._owned = http is None
        self._http = http or httpx.AsyncClient(
            headers=_HEADERS, timeout=timeout, follow_redirects=True,
        )
        self._key = api_key or os.getenv("FINANCE_BPS_API_KEY", "").strip()

    async def aclose(self) -> None:
        if self._owned:
            await self._http.aclose()

    def _require_key(self) -> None:
        if not self._key:
            raise FinanceError(
                ErrorCode.AUTHENTICATION_FAILED,
                "BPS WebAPI requires FINANCE_BPS_API_KEY",
                provider=self.name,
            )

    async def _get(self, path: str) -> Any:
        try:
            r = await self._http.get(f"{_BASE}{path}")
        except httpx.TimeoutException as e:
            raise FinanceError(ErrorCode.TIMEOUT, str(e), provider=self.name) from e
        except httpx.HTTPError as e:
            raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE, str(e),
                               provider=self.name) from e
        if r.status_code == 401 or r.status_code == 403:
            raise FinanceError(ErrorCode.AUTHENTICATION_FAILED,
                               f"BPS rejected key (HTTP {r.status_code})",
                               provider=self.name)
        if r.status_code >= 400:
            raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE,
                               f"BPS HTTP {r.status_code}", provider=self.name)
        try:
            return r.json()
        except ValueError as e:
            raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                               f"BPS non-JSON: {e}", provider=self.name) from e

    async def macro_indicator(self, indicator: str) -> MacroSeries:
        self._require_key()
        ind = indicator.lower()
        if ind == "gdp_growth":
            ind = "gdp"
        if ind == "cpi_yoy":
            ind = "cpi"
        if ind not in _VAR:
            raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                               f"BPS does not serve indicator {indicator!r}",
                               provider=self.name)
        var_id, unit, freq, desc = _VAR[ind]
        path = f"/list/model/data/lang/ind/domain/0000/var/{var_id}/key/{self._key}"
        payload = await self._get(path)

        # BPS returns data in `datacontent` keyed by "<var><period_id>".
        # `vervar`, `turvar`, `tahun`, `turtahun` describe periods.
        content = ((payload or {}).get("datacontent") or {})
        years = {str(t["val"]): t.get("label") for t in
                 (payload or {}).get("tahun") or []}
        subperiods = {str(t["val"]): t.get("label") for t in
                      (payload or {}).get("turtahun") or []}
        obs: list[MacroObservation] = []
        for key, val in content.items():
            f = _num(val)
            if f is None:
                continue
            year = _extract_year(key, years)
            subp = _extract_sub(key, subperiods)
            period = f"{year}-{subp}" if year and subp else (year or key)
            obs.append(MacroObservation(period=period, value=f, unit=unit))

        if not obs:
            raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                               f"BPS returned empty datacontent for {indicator}",
                               provider=self.name)

        obs.sort(key=lambda o: o.period)
        return MacroSeries(
            indicator=ind, source=self.name, unit=unit,
            observations=obs, frequency=freq, description=desc,
            attribution=self.attribution,
        )


def _num(v: Any) -> float | None:
    try:
        if v in (None, ""):
            return None
        f = float(str(v).replace(",", "."))
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _extract_year(key: str, years: dict[str, str]) -> str | None:
    # BPS keys look like "5370" — last 4 chars often carry a year id
    # that maps via `tahun`. Fallback: return None.
    for cand in (key[-4:], key[-3:], key[-2:]):
        if cand in years:
            return str(years[cand])
    return None


def _extract_sub(key: str, subs: dict[str, str]) -> str | None:
    for cand in (key[-2:], key[-1:]):
        if cand in subs:
            return str(subs[cand])
    return None
