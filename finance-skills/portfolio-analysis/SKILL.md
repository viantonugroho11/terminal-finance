---
name: portfolio-analysis
description: Analyze the user's portfolio — holdings, P&L, allocation, top movers. Use for "my portfolio", "how am I doing", "what happened to my portfolio today", "biggest position".
version: 0.1.0
author: Finance Hermes
license: AGPL-3.0-only
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, Portfolio, Analysis]
    related_skills: [risk-analysis, stock-analysis]
    requires_tools:
      - finance.portfolio_summary
      - finance.portfolio_holdings
      - finance.portfolio_allocation
      - finance.get_quote
---

# Portfolio Analysis

## When to Use

- "my portfolio", "how am I doing", "show holdings", "what's my biggest position"
- "portfolio today", "am I too concentrated"

## Procedure

Call in parallel:

1. `finance.portfolio_summary()` — totals
2. `finance.portfolio_holdings()` — per-position with live prices
3. `finance.portfolio_allocation()` — sector buckets

For "today" queries, also pull per-symbol `finance.get_quote(<SYM>)` — already included in holdings.

## Output Format

```
PORTFOLIO  [FACT]
  Market Value      $XXX,XXX
  Cost Basis        $XXX,XXX
  Unrealized P&L    +$X,XXX  (+X.XX%)
  Realized Income   +$X,XXX
  Positions         N

HOLDINGS  [FACT]
  Symbol   Qty    Avg Cost    Price    Mkt Value   P&L         Wt%
  NVDA     100    $450.00    $XXX     $XX,XXX     +$X,XXX     XX%
  ...

ALLOCATION  [FACT]
  Technology       XX%
  Healthcare       XX%
  ...

TOP MOVERS (today)  [CALCULATION]
  <sorted holdings by change_percent from get_quote>

READ  [ANALYSIS]
  Concentration / diversification / sector tilt read.

RISKS  [RISK]
  · concrete risks tied to weights or sectors

CONFIDENCE
```

## Safety

- Never make up transactions. If `portfolio_holdings` returns empty, tell the user the portfolio is empty and offer `finance.portfolio_add_transaction`.
- Never advise buy/sell for their positions. Present facts + interpretation only.
- P&L tagged `[FACT]` because it comes from deterministic service, not LLM math.
