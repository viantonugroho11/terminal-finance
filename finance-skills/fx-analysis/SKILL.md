---
name: fx-analysis
description: Forex — spot cross rates, JISDOR IDR reference, forward points via CIP, central-bank stance context. Use when user says "USDIDR", "kurs", "JISDOR", "forward FX", "cross rate".
version: 0.1.0
author: Finance Hermes
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, FX, Forward, Indonesia]
    related_skills: [macro-context, market-overview]
    requires_tools:
      - finance.get_fx_cross
      - finance.get_jisdor_rate
      - finance.get_fx_forward
      - finance.get_macro
---

# FX Analysis

Composed forex answer: spot, JISDOR reference (for IDR pairs),
forward points via covered interest parity, and central-bank stance
context (BI Rate for IDR).

## When to Use

- "USDIDR spot dan JISDOR"
- "forward 1M USDIDR"
- "EURUSD cross rate"
- "kurs referensi hari ini"

## Flow

1. `finance.get_fx_cross(base, quote)` for spot (Yahoo `X=X` symbol).
2. For IDR pairs: `finance.get_jisdor_rate(date=None)` for BI reference.
3. If user asks forward: `finance.get_fx_forward(base, quote, tenor_days=...)`
   with domestic-rate hint (`rate_dom_annual`) = BI Rate for IDR.
4. Compose: spot vs JISDOR delta (in points), forward + points, note
   which side is domestic ccy.

## Rules

- Forward points from `get_fx_forward` are ALWAYS derived via CIP —
  they are approximations, NOT tradable dealer quotes. Say so.
- JISDOR is a fixing (daily, once), not a live tick. If spot moved
  since fixing, do not blend.
- Domestic vs foreign: for USDIDR, IDR is domestic (dom rate = BI
  Rate), USD is foreign (for rate = SOFR proxy ≈ Fed Funds). Do not
  invert.
- Provenance `derived: true` on any forward output must be surfaced.
