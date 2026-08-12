---
name: stock-analysis
description: Multi-factor equity analysis — fundamentals, valuation, technicals, news, catalysts, risks. Use when user says "analyze <TICKER>", "research <TICKER>", or asks for opinion on a stock.
version: 0.1.0
author: Finance Hermes
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, Equity, Research, Analysis]
    related_skills: [crypto-analysis, market-overview, fundamental-analysis, technical-analysis]
    requires_tools:
      - finance.get_quote
      - finance.get_company
      - finance.get_financials
      - finance.get_technical
      - finance.search_news
---

# Stock Analysis

Structured equity analysis grounded ONLY in tool output. Never fabricate numbers, prices, ratios, or news.

## When to Use

- User says: "analyze NVDA", "what do you think about AAPL", "research TSLA", "should I look at MSFT"
- Any question requiring current stock fundamentals, valuation, technicals, or news

## Procedure

For symbol `<SYM>`, call finance MCP tools **in parallel**:

1. `finance.get_quote(<SYM>)` — current price + change
2. `finance.get_company(<SYM>)` — business overview
3. `finance.get_financials(<SYM>)` — valuation + margins + growth
4. `finance.get_technical(<SYM>, period="1y")` — SMA/EMA/RSI/MACD/volatility/drawdown
5. `finance.search_news(<SYM>, limit=8)` — recent headlines

Then synthesize the output below. Every numeric claim must trace to a tool result. If a field is null, say "not available" — do not guess.

## Output Format

```
<SYM> — <Company Name>
Sector · Industry

PRICE
  Price          $X.XX
  Change         +$X.XX (+X.XX%)
  Market Cap     $X.XXB

FUNDAMENTALS  [FACT]
  P/E (ttm)      X.XX
  Forward P/E    X.XX
  PEG            X.XX
  P/B            X.XX
  ROE            XX.X%
  Op Margin      XX.X%
  Rev Growth     XX.X%
  Debt/Equity    X.XX
  FCF            $X.XXB
  Beta           X.XX

TECHNICALS  [FACT]
  Last Close     $X.XX
  SMA 20/50/200  $X / $X / $X
  RSI (14)       XX.X
  MACD           X.XX (signal X.XX, hist X.XX)
  30d Vol (ann)  XX.X%
  Max Drawdown   -XX.X%

BUSINESS  [FACT]
  <2-3 line summary from get_company>

RECENT NEWS  [FACT]
  · <headline 1> — <publisher>
  · <headline 2> — <publisher>
  · ...

INTERPRETATION  [ANALYSIS — not fact]
  Valuation:   <cheap / fair / expensive vs peers/history — cite the ratio>
  Momentum:    <RSI/MACD/SMA read>
  Quality:     <margins + ROE read>
  Growth:      <rev/earnings growth read>

BULL CASE
  · <point 1 grounded in numbers above>
  · <point 2>

BEAR CASE
  · <point 1 grounded in numbers above>
  · <point 2>

RISKS  [RISK]
  · <specific risk tied to a metric or news item>

CONFIDENCE: <Low | Moderate | High>
  <one line: what would raise/lower it>
```

## Safety Rules

- **Never** state a price, ratio, or news headline that did not come from a tool call this turn.
- If a tool errors or returns null for a field, print "not available" — do not substitute training-data knowledge.
- Never recommend "buy" / "sell" / "hold". Present bull + bear + risks. User decides.
- Tag every section: `[FACT]` (from tools), `[ANALYSIS]` (your interpretation), `[RISK]` (uncertainty).
- If the symbol is invalid (tool returns error on quote), say so and stop — do not synthesize.

## Pitfalls

- yfinance returns `null` for many ratios on non-US listings — surface the gap, don't hide it.
- `dividendYield` from Yahoo is a fraction (0.015 = 1.5%). Multiply by 100 when displaying.
- News timestamps are epoch seconds on some paths, ISO on others — display as returned.

## Verification

Before sending output: confirm every number in the report appears in at least one tool result from this turn's message history.
