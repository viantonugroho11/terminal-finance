---
name: technical-analysis
description: Trend, momentum, volatility, drawdown from OHLCV. Use for "technical read on X", "chart", "trend", "is X overbought", "support/resistance context".
version: 0.1.0
author: Finance Hermes
license: AGPL-3.0-only
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, Equity, Technical]
    related_skills: [stock-analysis, equity-research]
    requires_tools:
      - finance.get_technical
      - finance.get_historical_prices
      - finance.get_quote
---

# Technical Analysis

Deterministic indicators. No fabricated levels, no fabricated patterns.

## When to Use

- "technical NVDA", "is BBCA overbought", "trend on TLKM"
- "recent price action", "chart read"

## Procedure

1. `finance.get_quote(<SYM>)` — last price + change
2. `finance.get_technical(<SYM>, period="1y")` — SMA(20/50/200), EMA20, RSI14, MACD, vol, drawdown

Optionally, if the user wants a specific lookback:

3. `finance.get_historical_prices(<SYM>, period=..., interval=...)`

## Output Format

```
<SYM> — Technicals ({period})

LAST [FACT]
  Price       X.XX    Change     +/- X.XX%
  Volume      X

TREND [FACT]
  SMA 20      X.XX    (price vs SMA: +/- X.X%)
  SMA 50      X.XX
  SMA 200     X.XX    (200d slope: rising / flat / falling)
  EMA 20      X.XX

MOMENTUM [FACT]
  RSI 14      XX.X    (>70 overbought, <30 oversold)
  MACD        X.XX    Signal X.XX    Hist X.XX

RISK [FACT]
  30d vol (ann)   XX.X%
  Max drawdown    -XX.X%

INTERPRETATION [ANALYSIS]
  Trend:      above/below 20/50/200 SMA; regime read
  Momentum:   RSI band + MACD cross direction
  Volatility: relative to peer / history (say "unavailable" if no peer)

SIGNALS [ANALYSIS]
  · <specific signal grounded in a value above>

RISKS [RISK]
  · Overbought (RSI > 70): pullback risk
  · Below 200 SMA: structural downtrend context
  · Recent drawdown > 20%: momentum unfavorable

CONFIDENCE
```

## Rules

- Never call a chart pattern (head-and-shoulders, cup-and-handle, etc.). Tools do not detect them.
- Support/resistance: only cite recent visible highs/lows from history if explicitly requested — do NOT hallucinate levels.
- RSI/MACD thresholds are conventional (not sacred). Note the value; user interprets.
- Never state a "buy signal" — describe the indicator, not the action.
- If `get_technical` errors: apologize, cite the error code, stop.
