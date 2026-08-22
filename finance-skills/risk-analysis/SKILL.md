---
name: risk-analysis
description: Portfolio risk — concentration, volatility, drawdown, sector tilt. Use for "portfolio risk", "am I concentrated", "biggest risk", "which position hurts most".
version: 0.1.0
author: Finance Hermes
license: AGPL-3.0-only
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, Portfolio, Risk]
    related_skills: [portfolio-analysis]
    requires_tools:
      - finance.portfolio_risk
      - finance.portfolio_allocation
---

# Risk Analysis

## When to Use

- "portfolio risk", "biggest risk", "am I too concentrated"
- "which position is dragging me down", "drawdown"

## Procedure

1. `finance.portfolio_risk()` — HHI, top-5 weight, per-position vol + drawdown
2. `finance.portfolio_allocation()` — sector concentration

## Output Format

```
CONCENTRATION  [FACT]
  HHI                     XXXX   (0–10000; >2500 = concentrated)
  Top-5 Weight            XX.X%
  Positions               N

PER-POSITION  [FACT]
  Symbol   Weight   30d Vol (ann)   6mo Max DD
  NVDA     XX%      XX.X%           -XX.X%
  ...  (sort by weight desc)

SECTOR TILT  [FACT]
  Technology       XX%
  ...

INTERPRETATION  [ANALYSIS]
  Concentration read (HHI + top-5)
  Which positions dominate risk (weight × volatility)
  Sector tilt vs balanced

RISKS  [RISK]
  · Named position + why it's risky (weight, vol, drawdown)

CONFIDENCE
```

## Rules

- HHI thresholds: <1500 diversified, 1500–2500 moderate, >2500 concentrated.
- Never state a Sharpe / VaR / beta the tool didn't return. Add later if provider exposes.
