---
name: market-overview
description: Snapshot of global markets — indices, crypto, safe havens. Use for "market", "how are markets", "morning briefing".
version: 0.1.0
author: Finance Hermes
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, Markets, Briefing]
    related_skills: [stock-analysis, crypto-analysis]
    requires_tools:
      - finance.get_market_overview
      - finance.search_news
    blueprint:
      schedule: "0 8 * * 1-5"
      deliver: origin
      prompt: "Run the market-overview skill and deliver the morning briefing."
      no_agent: false
---

# Market Overview

## When to Use

- "market", "how are markets today", "morning briefing", "market snapshot"

## Procedure

1. `finance.get_market_overview()` — one call, returns S&P/NASDAQ/DOW/BTC/ETH/GOLD/OIL/DXY
2. `finance.search_news("stock market", limit=5)` — top headlines

## Output Format

```
MARKET SNAPSHOT  [FACT]

Equities
  S&P 500     X,XXX  +X.XX%
  NASDAQ      X,XXX  +X.XX%
  DOW         X,XXX  +X.XX%

Crypto
  BTC         $XXX,XXX  +X.XX%
  ETH         $X,XXX    +X.XX%

Commodities / FX
  GOLD        $X,XXX  +X.XX%
  OIL         $XX.XX  +X.XX%
  DXY         XXX.XX  +X.XX%

TOP NEWS  [FACT]
  · headline — publisher

READ  [ANALYSIS]
  Risk-on / risk-off / mixed. Cite the moves that justify it.
```

## Safety

Never state a level or % not returned by the tool. If a symbol errored, print "n/a" for it.
