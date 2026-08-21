"""Deterministic technical indicators. Never ask LLM to compute these."""
from __future__ import annotations

import pandas as pd

from .models import Candle


def _closes(candles: list[Candle]) -> pd.Series:
    return pd.Series([c.close for c in candles], dtype=float)


def sma(candles: list[Candle], period: int = 20) -> float | None:
    s = _closes(candles)
    if len(s) < period:
        return None
    return float(s.tail(period).mean())


def ema(candles: list[Candle], period: int = 20) -> float | None:
    s = _closes(candles)
    if len(s) < period:
        return None
    return float(s.ewm(span=period, adjust=False).mean().iloc[-1])


def rsi(candles: list[Candle], period: int = 14) -> float | None:
    s = _closes(candles)
    if len(s) < period + 1:
        return None
    delta = s.diff().dropna()
    gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    last_gain, last_loss = float(gain.iloc[-1]), float(loss.iloc[-1])
    if last_loss == 0:
        return 100.0 if last_gain > 0 else 50.0
    rs = last_gain / last_loss
    return float(100 - (100 / (1 + rs)))


def macd(candles: list[Candle]) -> dict[str, float] | None:
    s = _closes(candles)
    if len(s) < 35:
        return None
    ema12 = s.ewm(span=12, adjust=False).mean()
    ema26 = s.ewm(span=26, adjust=False).mean()
    line = ema12 - ema26
    signal = line.ewm(span=9, adjust=False).mean()
    return {
        "macd": float(line.iloc[-1]),
        "signal": float(signal.iloc[-1]),
        "histogram": float((line - signal).iloc[-1]),
    }


def volatility(candles: list[Candle], period: int = 30) -> float | None:
    s = _closes(candles)
    if len(s) < period:
        return None
    returns = s.pct_change().dropna().tail(period)
    return float(returns.std() * (252 ** 0.5) * 100)


def drawdown(candles: list[Candle]) -> float | None:
    s = _closes(candles)
    if s.empty:
        return None
    peak = s.cummax()
    dd = (s / peak - 1) * 100
    return float(dd.min())


def summary(candles: list[Candle]) -> dict:
    return {
        "sma_20": sma(candles, 20),
        "sma_50": sma(candles, 50),
        "sma_200": sma(candles, 200),
        "ema_20": ema(candles, 20),
        "rsi_14": rsi(candles, 14),
        "macd": macd(candles),
        "volatility_30d_annualized_pct": volatility(candles, 30),
        "max_drawdown_pct": drawdown(candles),
        "last_close": candles[-1].close if candles else None,
        "candles_used": len(candles),
    }
