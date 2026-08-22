---
name: valuation-analysis
description: Deterministic DCF valuation for equities — projects FCF, applies CAPM/WACC, terminal value, sensitivity. Use when user asks "valuation", "intrinsic value", "fair value", "is X overvalued/undervalued", "DCF".
version: 0.1.0
author: Finance Hermes
license: AGPL-3.0-only
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, Valuation, DCF]
    related_skills: [stock-analysis, fundamental-analysis]
    requires_tools:
      - finance.valuation_dcf
      - finance.valuation_sensitivity
      - finance.get_fundamentals
      - finance.get_financial_statements
      - finance.get_company_profile
      - finance.get_quote
---

# Valuation Analysis (DCF)

Deterministic two-stage DCF. All math lives in `finance_mcp.valuation`; this skill only orchestrates + interprets. Never invent numbers.

## When to Use

- "valuation dari NVDA", "fair value BBCA", "is TLKM undervalued?", "DCF ASII"
- Any question comparing market price to intrinsic value

## Procedure

1. `finance.get_quote(<SYM>)` — current price (context)
2. `finance.get_company_profile(<SYM>)` — market cap
3. `finance.get_fundamentals(<SYM>)` — beta
4. `finance.valuation_dcf(<SYM>)` — base-case DCF with auto-derived growth + CAPM discount
5. `finance.valuation_sensitivity(<SYM>)` — WACC × terminal-growth grid

The tools return `{data, provenance}`. `data.inputs` shows every assumption used (discount rate, growth, beta, net debt). Cite them.

## Assumptions Defaults

Base case uses:
- **Discount rate**: CAPM with `rf=4.5%`, `ERP=5.5%`, beta from `get_fundamentals`. Fallback beta=1.0.
- **Growth rate**: CAGR of historical Free Cash Flow (3y). Fallback 5%.
- **Terminal growth**: 3% (long-run nominal GDP proxy).
- **Projection horizon**: 5 years.
- **Net debt**: `total_debt − cash` from latest balance sheet.

If the user gives specific assumptions, pass them explicitly:
`valuation_dcf(<SYM>, discount_rate=0.10, terminal_growth=0.025, growth_rate=0.08, projection_years=7)`.

## Output Format

```
<SYM> — Valuation (DCF)

CURRENT
  Price          $X.XX    Market Cap  $X.XXB

ASSUMPTIONS  [FACT — from tool inputs]
  Base FCF (last)      $X.XXB
  Growth (5y)          XX.X%    (derived: XX.X% CAGR; override: XX.X%)
  Discount rate (WACC) X.XX%    (CAPM: rf=4.5% + β·5.5%; β=X.X)
  Terminal growth      X.XX%
  Projection horizon   N years
  Net debt             $X.XXB

DCF RESULT  [FACT]
  PV of explicit FCF   $X.XXB
  Terminal value       $X.XXB   (PV: $X.XXB)
  Enterprise value     $X.XXB
  Equity value         $X.XXB
  Upside vs market cap +XX.X%   [FACT — computed by tool]

SENSITIVITY (Enterprise Value)  [FACT — from valuation_sensitivity]
                g=1%     g=2%     g=3%     g=4%
  r=8%       $X.XB    $X.XB    $X.XB    $X.XB
  r=9%       $X.XB    $X.XB    $X.XB    $X.XB
  r=10%      $X.XB    $X.XB    $X.XB    $X.XB
  r=11%      $X.XB    $X.XB    $X.XB    $X.XB
  r=12%      $X.XB    $X.XB    $X.XB    $X.XB

INTERPRETATION  [ANALYSIS — not fact]
  <upside/downside vs market>
  <what has to be true for base case to hold>
  <which assumption the value is most sensitive to (widest row/col spread)>

RISKS TO VALUATION  [RISK]
  · Terminal-value dominance (share of EV): XX%
  · Historical FCF volatility
  · Bank/utility: DCF less reliable — recommend alternative (P/B, DDM)

CONFIDENCE: <Low | Moderate | High>
  Low if:  FCF series short (<3y), heavily negative, or growth CAGR fails
  High if: 5+ years of positive FCF, stable growth, moderate net debt

SOURCES
  Valuation math: finance_mcp.valuation (deterministic)
  Statements / Fundamentals / Company: <provenance.source per tool>
```

## Safety Rules

- Never state a "fair value" not returned by the tool.
- Always show the assumptions block — DCF results are unfalsifiable without them.
- Do NOT recommend "buy" / "sell". Present upside vs market + risks; user decides.
- If `valuation_dcf` returns `DATA_UNAVAILABLE` (no FCF history), say so and stop. Do NOT substitute a heuristic multiplier.
- For financials (banks, insurance) DCF-on-FCF is unreliable — explicitly say so and recommend P/B, DDM, or residual-income methods instead.
- For IDX symbols: report values in the currency the tool returned (IDR for `.JK`).

## Pitfalls

- `growth_rate=None` uses FCF CAGR; if FCF series has a big one-off (asset sale), CAGR misleads. Check `inputs.derived_growth_rate` vs `inputs.growth_rate` and note if you overrode.
- `discount_rate` from CAPM requires beta; provider may return null → tool falls back to β=1.0. Note this.
- Terminal value share > 75% of EV = base case sensitive to `terminal_growth` — flag it in RISKS.
- Reverse-DCF (`implied_growth` in `finance_mcp.valuation`) is available to library callers but not yet exposed as a tool.

## Verification

Every number in the report must appear in a tool result this turn. Assumptions and growth mismatches must be surfaced, not hidden.
