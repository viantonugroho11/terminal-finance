---
name: macro-context
description: Indonesian macro snapshot (BI-Rate, JISDOR, inflation, GDP, unemployment, banking SPI) framed against an equity or thesis. Use for "macro Indonesia", "bagaimana kondisi ekonomi", "pengaruh BI Rate ke bank", "how does macro affect X".
version: 0.1.0
author: Finance Hermes
license: AGPL-3.0-only
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, Macro, Indonesia]
    related_skills: [stock-analysis, equity-research, market-overview]
    requires_tools:
      - finance.get_macro
---

# Macro Context (Indonesia)

Bundle the Indonesian macro block and interpret it either standalone or
against a named equity/sector.

## When to Use

- "kondisi makro Indonesia", "bagaimana ekonomi Indonesia"
- "pengaruh BI Rate ke bank" — anchors interpretation to sector
- "outlook rupiah", "berapa inflasi terakhir"
- Any equity analysis where macro matters (banks, exporters, retailers)

## Procedure

Call in parallel:

1. `finance.get_macro("bi_rate")`
2. `finance.get_macro("jisdor")` — USD/IDR
3. `finance.get_macro("inflation")`
4. `finance.get_macro("gdp")`
5. `finance.get_macro("unemployment")`
6. `finance.get_macro("banking_spi")` — NPL/CAR/NIM aggregates (may return DATA_UNAVAILABLE if OJK snapshot not configured)

Each reply carries `provenance.attribution` (Bank Indonesia / BPS / OJK). Cite it.

## Output Format

```
Indonesia Macro — as of {latest observation date per series}

RATES / FX [FACT]
  BI-Rate         X.XX%     (YYYY-MM)          [attr: Bank Indonesia]
  USD/IDR (JISDOR) XX,XXX   (YYYY-MM-DD)       [attr: Bank Indonesia]

PRICES [FACT]
  Inflation YoY   X.XX%     (YYYY-MM)          [attr: BPS]

GROWTH / LABOR [FACT]
  GDP growth      X.XX%     (YYYY-Q)           [attr: BPS]
  Unemployment    X.XX%     (YYYY-Q)           [attr: BPS]

BANKING [FACT — if OJK snapshot configured]
  NPL             X.XX%     (YYYY-MM)          [attr: OJK SPI]
  CAR             XX.X%     (YYYY-MM)          [attr: OJK SPI]
  NIM             X.XX%     (YYYY-MM)          [attr: OJK SPI]

REGIME READ [ANALYSIS]
  Rates trajectory:   cutting / holding / hiking (cite last N observations)
  FX pressure:        strengthening / stable / depreciating (cite JISDOR trend)
  Price pressure:     within BI target (2%-4%) / above / below (cite inflation)
  Growth pulse:       above / at / below trend (~5%)
  Banking system:     healthy / stressed (cite NPL vs 3% guideline)

IMPACT — <named equity / sector>  [ANALYSIS — only when user names one]
  Banks (BBCA/BBRI/BMRI/BBNI):
    · BI-Rate cut → NIM pressure, loan growth tailwind
    · BI-Rate hike → NIM expansion (asset-sensitive), CoC risk
  Consumer / retail:
    · Rate cuts → discretionary spend up
    · IDR weakness → imported cost pressure
  Exporters (mining, palm):
    · IDR weakness → margin tailwind
    · Rate hikes → less relevant

RISKS [RISK]
  · Rate regime shift within 3–6 months
  · IDR breach of BI intervention band
  · Inflation above target for 3+ consecutive months

CONFIDENCE
  Low if: OJK block unavailable + banking equity thesis
  High if: all six series fresh + coherent story
```

## Rules

- Never state a macro figure not returned by `get_macro`. If a series errored, print "n/a — <error code>".
- Every figure must carry its date + attribution.
- The IMPACT block only fires when the user named an equity or sector — do not editorialize otherwise.
- Never predict rates ("BI will cut in Q4"). Describe trajectory of observed data only.
- If banking_spi returned `DATA_UNAVAILABLE`, note that the OJK snapshot needs `FINANCE_OJK_SPI_PATH` and continue with the other five series.
