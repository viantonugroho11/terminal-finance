"""Crypto multi-venue provider — ADR-0031.

DEVIATION FROM ADR: ADR called for `ccxt` wrapping 4+ exchanges. v1
uses direct httpx to public REST endpoints of Binance + Indodax only,
which covers the important IDR-pair use case with zero heavy deps.
Add ccxt later when Kraken/Coinbase demand materialises.

All endpoints used are public (no keys, no signing). Rate-limit aware
via short caches upstream. `fetcher` is injectable so tests do not
hit the network.
"""
from __future__ import annotations

from typing import Any, Callable

import httpx

from ..errors import ErrorCode, FinanceError
from ..models import (
    CryptoCandle,
    CryptoOhlcv,
    CryptoOrderBook,
    CryptoOrderBookLevel,
    StablecoinPeg,
)

_UA = "finance-mcp/0.2 (+crypto)"
_HEADERS = {"User-Agent": _UA, "Accept": "application/json"}

BINANCE_BASE = "https://api.binance.com"
INDODAX_BASE = "https://indodax.com/api"


# Timeframe → Binance interval mapping.
_TF_BINANCE = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w",
}


def _stablecoin(sym: str) -> bool:
    return sym.upper() in {"USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD"}


class CryptoProvider:
    name = "crypto"
    tier = "primary"
    markets = frozenset({"CRYPTO"})
    capabilities = frozenset({
        "crypto_ohlcv_venue", "crypto_orderbook", "stablecoin_peg",
    })
    requires_api_key = False

    def __init__(self, http: httpx.AsyncClient | None = None,
                 *, timeout: float = 15.0,
                 fetcher: Callable[..., Any] | None = None):
        self._owned = http is None
        self._http = http or httpx.AsyncClient(
            headers=_HEADERS, timeout=timeout, follow_redirects=True,
        )
        self._fetcher = fetcher

    async def aclose(self) -> None:
        if self._owned:
            await self._http.aclose()

    async def _get_json(self, url: str, params: dict | None = None,
                        *, symbol: str | None = None) -> Any:
        if self._fetcher is not None:
            return await self._fetcher(url, params or {})
        try:
            r = await self._http.get(url, params=params or {})
        except httpx.HTTPError as e:
            raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE,
                               f"crypto HTTP: {e}",
                               provider=self.name, symbol=symbol) from e
        if r.status_code >= 400:
            raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE,
                               f"crypto HTTP {r.status_code}",
                               provider=self.name, symbol=symbol)
        try:
            return r.json()
        except ValueError as e:
            raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                               f"crypto non-JSON: {e}",
                               provider=self.name, symbol=symbol) from e

    # ── OHLCV ────────────────────────────────────────────────────────

    async def ohlcv(self, symbol: str, *, exchange: str = "binance",
                    timeframe: str = "1h", limit: int = 200) -> CryptoOhlcv:
        ex = exchange.lower()
        sym = symbol.upper()
        if ex == "binance":
            interval = _TF_BINANCE.get(timeframe, "1h")
            payload = await self._get_json(
                f"{BINANCE_BASE}/api/v3/klines",
                {"symbol": sym, "interval": interval, "limit": limit},
                symbol=sym,
            )
            candles = [self._binance_candle(row) for row in (payload or [])]
        elif ex == "indodax":
            # Indodax uses lowercase pair like btcidr
            pair = sym.lower()
            payload = await self._get_json(
                f"{INDODAX_BASE}/tradingview/history",
                {"symbol": pair, "resolution":
                    self._indodax_res(timeframe), "from": 0, "to": 9_999_999_999},
                symbol=sym,
            )
            candles = self._indodax_candles(payload, limit)
        else:
            raise FinanceError(
                ErrorCode.PROVIDER_UNAVAILABLE,
                f"exchange {exchange!r} not implemented in v1 "
                "(binance, indodax only)",
                provider=self.name, symbol=sym,
            )
        return CryptoOhlcv(symbol=sym, exchange=ex,
                           timeframe=timeframe, candles=candles)

    # ── Order book ───────────────────────────────────────────────────

    async def orderbook(self, symbol: str, *, exchange: str = "binance",
                        depth: int = 20) -> CryptoOrderBook:
        ex = exchange.lower()
        sym = symbol.upper()
        if ex == "binance":
            payload = await self._get_json(
                f"{BINANCE_BASE}/api/v3/depth",
                {"symbol": sym, "limit": min(depth, 100)}, symbol=sym,
            )
            bids = [CryptoOrderBookLevel(float(p), float(q))
                    for p, q in (payload or {}).get("bids", [])[:depth]]
            asks = [CryptoOrderBookLevel(float(p), float(q))
                    for p, q in (payload or {}).get("asks", [])[:depth]]
        elif ex == "indodax":
            pair = sym.lower()
            payload = await self._get_json(
                f"{INDODAX_BASE}/depth/{pair}", symbol=sym,
            )
            bids = [CryptoOrderBookLevel(float(p), float(q))
                    for p, q in (payload or {}).get("buy", [])[:depth]]
            asks = [CryptoOrderBookLevel(float(p), float(q))
                    for p, q in (payload or {}).get("sell", [])[:depth]]
        else:
            raise FinanceError(
                ErrorCode.PROVIDER_UNAVAILABLE,
                f"exchange {exchange!r} not implemented",
                provider=self.name, symbol=sym,
            )
        return CryptoOrderBook(symbol=sym, exchange=ex, bids=bids, asks=asks)

    # ── Stablecoin peg ───────────────────────────────────────────────

    async def stablecoin_peg(self, symbol: str, *,
                             exchange: str = "binance") -> StablecoinPeg:
        base = symbol.upper()
        if not _stablecoin(base):
            raise FinanceError(
                ErrorCode.INVALID_SYMBOL,
                f"{base} is not a recognized stablecoin",
                provider=self.name, symbol=base,
            )
        # Try USDT quote first, then USDC as fallback for USD proxy.
        candidates = [f"{base}USDT", f"{base}USDC"] if base != "USDT" else ["USDCUSDT"]
        for c in candidates:
            try:
                payload = await self._get_json(
                    f"{BINANCE_BASE}/api/v3/ticker/price",
                    {"symbol": c}, symbol=base,
                )
                price = float((payload or {}).get("price") or 0.0)
                if price <= 0:
                    continue
                # If quote is USDT/USDC, use price directly as USD proxy.
                return StablecoinPeg(
                    symbol=base, exchange=exchange.lower(),
                    price=price, deviation_bps=(price - 1.0) * 10_000.0,
                )
            except FinanceError:
                continue
        raise FinanceError(
            ErrorCode.DATA_UNAVAILABLE,
            f"no peg price found for {base}",
            provider=self.name, symbol=base,
        )

    # ── parsers ──────────────────────────────────────────────────────

    def _binance_candle(self, row: list[Any]) -> CryptoCandle:
        # [openTime, open, high, low, close, volume, closeTime, ...]
        from datetime import datetime, timezone
        return CryptoCandle(
            ts=datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc)
                      .isoformat(),
            open=float(row[1]), high=float(row[2]), low=float(row[3]),
            close=float(row[4]), volume=float(row[5]),
        )

    def _indodax_res(self, timeframe: str) -> str:
        return {"1m": "1", "5m": "5", "15m": "15", "30m": "30",
                "1h": "60", "4h": "240", "1d": "1D"}.get(timeframe, "60")

    def _indodax_candles(self, payload: Any, limit: int) -> list[CryptoCandle]:
        # Indodax tradingview format: {t:[], o:[], h:[], l:[], c:[], v:[]}
        from datetime import datetime, timezone
        if not isinstance(payload, dict):
            return []
        t = payload.get("t") or []
        o = payload.get("o") or []
        h = payload.get("h") or []
        l = payload.get("l") or []
        c = payload.get("c") or []
        v = payload.get("v") or []
        n = min(len(t), len(o), len(h), len(l), len(c), len(v))
        out: list[CryptoCandle] = []
        for i in range(max(0, n - limit), n):
            out.append(CryptoCandle(
                ts=datetime.fromtimestamp(int(t[i]), tz=timezone.utc).isoformat(),
                open=float(o[i]), high=float(h[i]), low=float(l[i]),
                close=float(c[i]), volume=float(v[i]),
            ))
        return out
