---
name: crypto-analysis
description: Crypto asset analysis — price, technicals, news. Use when user asks about BTC, ETH, SOL, or any "<TICKER>-USD" pair.
version: 0.1.0
author: Finance Hermes
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, Crypto, Analysis]
    related_skills: [stock-analysis, market-overview]
    requires_tools:
      - finance.get_quote
      - finance.get_historical_prices
      - finance.get_technical
      - finance.search_news
---

# Crypto Analysis

## When to Use

- "analyze BTC", "what's going on with ETH", "SOL technical read"
- Any crypto ticker — normalize to `<SYM>-USD` (BTC → BTC-USD, ETH → ETH-USD).

## Procedure

For symbol `<SYM>-USD`, call in parallel:

1. `finance.get_quote(<SYM>-USD)`
2. `finance.get_technical(<SYM>-USD, period="6mo")`
3. `finance.search_news(<SYM>-USD, limit=6)`

## Output Format

```
<SYM> — <name>

PRICE  [FACT]
  Price      $X
  24h        +X.XX%

TECHNICALS  [FACT]
  SMA 20/50/200
  RSI (14)
  MACD
  30d Vol (annualized)
  Max Drawdown (6mo)

NEWS  [FACT]
  · headline — publisher

INTERPRETATION  [ANALYSIS]
  Trend / momentum / volatility read

RISKS  [RISK]
  · crypto-specific risks

CONFIDENCE
```

## Safety Rules

Same as stock-analysis: every number must come from a tool call this turn. Never state fundamentals — crypto has no P/E. Never predict price.
