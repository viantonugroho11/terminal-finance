---
name: fundamental-analysis
description: Deep fundamentals — ratios, statements, quality, growth. Use for "fundamentals of X", "analisis fundamental X", "how strong is X's balance sheet", "is X profitable".
version: 0.1.0
author: Finance Hermes
license: AGPL-3.0-only
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, Equity, Fundamental]
    related_skills: [stock-analysis, valuation-analysis, equity-research]
    requires_tools:
      - finance.get_fundamentals
      - finance.get_financial_statements
      - finance.get_company_profile
      - finance.get_sec_facts
---

# Fundamental Analysis

Grounded ratio / statement / quality read for one equity. No prices, no charts.

## When to Use

- "fundamentals of NVDA", "analisis fundamental BBCA"
- "is X's balance sheet strong", "quality of earnings", "growth trajectory"

## Procedure

Call in parallel:

1. `finance.get_company_profile(<SYM>)`
2. `finance.get_fundamentals(<SYM>)` — includes IDX banking ratios (NIM/NPL/CAR/LDR/CASA) when routed to `idx`
3. `finance.get_financial_statements(<SYM>)`

For US symbols, optionally cross-check load-bearing figures against SEC primary:

4. `finance.get_sec_facts(<SYM>, "Revenues")` — if fundamentals numbers look off
5. `finance.get_sec_facts(<SYM>, "NetIncomeLoss")` — same

If SEC and Yahoo disagree, prefer SEC (higher `provenance.tier`).

## Output Format

```
<SYM> — Fundamentals

VALUATION [FACT]
  P/E ttm       X.XX     P/E fwd   X.XX
  PEG           X.XX     P/B       X.XX     P/S    X.XX
  Div yield     XX.X%    Beta      X.XX

PROFITABILITY [FACT]
  Op margin     XX.X%    Net margin   XX.X%
  ROE           XX.X%    ROA          XX.X%

GROWTH [FACT]
  Rev growth    XX.X%    Earnings growth   XX.X%
  FCF (last)    $X.XXB

BALANCE SHEET [FACT]
  Debt/Equity   X.XX     Current ratio    X.XX
  Total debt    $X.XXB   Cash             $X.XXB   Net debt   $X.XXB

BANKING METRICS [FACT — IDX banks only, when returned]
  NIM   X.XX%   NPL   X.XX%   CAR   X.XX%   LDR   XX.X%   CASA   XX.X%

3Y TREND [FACT — from statements]
  Revenue      Y-2: $X.XB   Y-1: $X.XB   Y0: $X.XB
  Net income   Y-2: $X.XB   Y-1: $X.XB   Y0: $X.XB
  FCF          Y-2: $X.XB   Y-1: $X.XB   Y0: $X.XB

INTERPRETATION [ANALYSIS]
  Valuation:     cheap / fair / expensive vs history + peers, cite the ratio
  Profitability: high / average / low, cite margin/ROE
  Growth:        accelerating / stable / decelerating, cite CAGR
  Balance sheet: net cash / moderate / leveraged, cite D/E + net debt
  Quality:       earnings vs cashflow gap (accruals), FCF conversion

STRENGTHS [ANALYSIS]
  · <ratio-grounded>
WEAKNESSES [ANALYSIS]
  · <ratio-grounded>

CONFIDENCE
  Low if: <3 years of data, null critical ratios, provenance.tier=scraped
  High if: 3+ years, primary source (idx / sec) confirmed

SOURCES
  <provider per tool>
```

## Rules

- Every number cites its tool result. No prose numbers.
- If a ratio is null, print "n/a" — do not compute it from raw statements without stating you did.
- For banks: skip generic D/E / current-ratio commentary (not meaningful); lead with NIM/NPL/CAR.
- Never recommend buy/sell. Present strengths + weaknesses.
