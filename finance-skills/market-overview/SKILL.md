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
      - finance.get_market_movers
      - finance.get_quote
      - finance.get_macro
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
- Indonesian variants: "pasar", "IHSG hari ini", "kondisi pasar", "briefing pagi"

## Procedure

Call in parallel:

1. `finance.get_market_overview()` — S&P/NASDAQ/DOW/Russell/VIX/BTC/ETH/GOLD/OIL/DXY
2. `finance.get_market_movers()` — top gainers / losers / most active
3. **Indonesian block** (always include when producing an ID-oriented briefing, or when the user asks in Indonesian):
   - `finance.get_idx_overview()` — IHSG + LQ45 + IDX sector performance in one call (IDX-native)
   - `finance.get_idx_movers()` — IDX top gainers / losers / most active
   - `finance.get_macro("bi_rate")` — latest BI-Rate observation
   - `finance.get_macro("jisdor")` — latest USD/IDR reference rate
   - `finance.get_macro("inflation")` — latest headline inflation
   - Fallback if `get_idx_overview` errors: `finance.get_quote("^JKSE")` via Yahoo.
4. `finance.search_news("stock market", limit=5)` — top headlines

Every reply carries `{data, provenance}`. If a bucket is empty or a tool
returns `{error: {...}}`, print "n/a" for that section — do not fabricate.

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

Indonesia  [FACT — omit block if all sub-calls errored]
  IHSG        X,XXX  +X.XX%
  LQ45        X,XXX  +X.XX%
  BI-Rate     X.XX%  (as of YYYY-MM)
  USD/IDR     XX,XXX (JISDOR, YYYY-MM-DD)
  Inflation   X.XX%  YoY (YYYY-MM)

MOVERS  [FACT]
  Top Gainers   SYM +XX.X%
  Top Losers    SYM -XX.X%
  Most Active   SYM  X.X%  (vol)

TOP NEWS  [FACT]
  · headline — publisher

READ  [ANALYSIS]
  Risk-on / risk-off / mixed. Cite the moves that justify it.
```

## Safety

Never state a level or % not returned by the tool. If a symbol errored, print "n/a" for it.
Every macro figure must cite `provenance.attribution` (Bank Indonesia / BPS / OJK). If `get_macro` returns `DATA_UNAVAILABLE`, print "n/a — source unavailable this run" and continue with the equities block.
