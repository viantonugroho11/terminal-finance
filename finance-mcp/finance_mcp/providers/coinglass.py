"""Coinglass derivatives provider — ADR-0031.

Public tier is rate-limited; COINGLASS_API_KEY promotes to paid tier
when set. Fetcher-injectable for tests.
"""
from __future__ import annotations
import os
from typing import Any, Callable

import httpx

from ..errors import FinanceError, ErrorCode
from ..models import PerpFunding, PerpOpenInterest


_BASE = "https://open-api-v3.coinglass.com"


class CoinglassProvider:
    name = "coinglass"
    tier = "primary"
    markets = frozenset({"CRYPTO"})
    capabilities = frozenset({
        "crypto_funding", "crypto_open_interest",
    })
    requires_api_key = False   # optional; free tier works without

    def __init__(self, http: httpx.AsyncClient | None = None,
                 *, timeout: float = 15.0,
                 fetcher: Callable[..., Any] | None = None,
                 api_key: str | None = None):
        self._owned = http is None
        self._api_key = api_key or os.getenv("COINGLASS_API_KEY")
        headers = {"User-Agent": "finance-mcp/0.2",
                   "Accept": "application/json"}
        if self._api_key:
            headers["CG-API-KEY"] = self._api_key
        self._http = http or httpx.AsyncClient(
            headers=headers, timeout=timeout, follow_redirects=True,
        )
        self._fetcher = fetcher

    async def aclose(self) -> None:
        if self._owned:
            await self._http.aclose()

    async def _get_json(self, path: str, params: dict | None = None,
                        *, symbol: str | None = None) -> Any:
        if self._fetcher is not None:
            return await self._fetcher(path, params or {})
        try:
            r = await self._http.get(f"{_BASE}{path}", params=params or {})
        except httpx.HTTPError as e:
            raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE,
                               f"coinglass HTTP: {e}",
                               provider=self.name, symbol=symbol) from e
        if r.status_code == 429:
            raise FinanceError(ErrorCode.RATE_LIMITED,
                               "coinglass rate limited (add COINGLASS_API_KEY)",
                               provider=self.name, symbol=symbol)
        if r.status_code >= 400:
            raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE,
                               f"coinglass HTTP {r.status_code}",
                               provider=self.name, symbol=symbol)
        try:
            return r.json()
        except ValueError as e:
            raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                               f"coinglass non-JSON: {e}",
                               provider=self.name, symbol=symbol) from e

    async def perp_funding(self, symbol: str, *,
                           exchange: str = "Binance") -> PerpFunding:
        payload = await self._get_json(
            "/api/futures/funding-rate/history",
            {"symbol": symbol.upper(), "exchange": exchange, "limit": 1},
            symbol=symbol,
        )
        data = (payload or {}).get("data") or []
        if not data:
            raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                               f"no funding for {symbol}",
                               provider=self.name, symbol=symbol)
        row = data[0]
        return PerpFunding(
            symbol=symbol.upper(), exchange=exchange.lower(),
            rate=float(row.get("fundingRate") or row.get("rate") or 0.0),
            next_funding_ts=row.get("nextFundingTime")
                              or row.get("nextTime"),
        )

    async def perp_open_interest(self, symbol: str, *,
                                 exchange: str = "Binance") -> PerpOpenInterest:
        payload = await self._get_json(
            "/api/futures/open-interest",
            {"symbol": symbol.upper(), "exchange": exchange},
            symbol=symbol,
        )
        data = (payload or {}).get("data") or {}
        if isinstance(data, list) and data:
            data = data[0]
        if not data:
            raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                               f"no OI for {symbol}",
                               provider=self.name, symbol=symbol)
        return PerpOpenInterest(
            symbol=symbol.upper(), exchange=exchange.lower(),
            oi_base=_maybe_float(data.get("oiBase") or data.get("openInterest")),
            oi_usd=_maybe_float(data.get("oiUsd") or data.get("openInterestAmount")),
            change_24h_pct=_maybe_float(data.get("h24Change")
                                        or data.get("oiChangePercent24h")),
        )


def _maybe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
