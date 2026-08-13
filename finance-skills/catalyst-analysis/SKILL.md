---
name: catalyst-analysis
description: Recent news, disclosures, corporate actions, SEC filings, IPOs. Use for "what happened with X", "any news", "recent filings", "corp action", "why is X moving".
version: 0.1.0
author: Finance Hermes
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, Equity, Catalyst, News]
    related_skills: [stock-analysis, equity-research]
    requires_tools:
      - finance.search_news
      - finance.get_disclosures
      - finance.get_corporate_actions
      - finance.get_dividends
      - finance.get_sec_filings
      - finance.get_ipo_calendar
---

# Catalyst Analysis

Assembles recent signals per symbol from news + disclosures + corp
actions + filings. Facts only. No thesis synthesis (that's `equity-research`).

## When to Use

- "any news on NVDA", "apa yang terjadi dengan BBCA", "why is TLKM moving"
- "recent filings", "corporate action", "dividend announcement"
- "IPO calendar" (no symbol)

## Procedure

Per-symbol calls in parallel:

1. `finance.search_news(<SYM>, limit=8)`
2. `finance.get_corporate_actions(<SYM>)` — splits, rights, bonus, dividends (IDX only)
3. `finance.get_dividends(<SYM>)` — dividend history
4. `finance.get_disclosures(<SYM>, limit=10)` — IDX only
5. `finance.get_sec_filings(<SYM>, limit=5)` — US only (skip on IDX)

Untargeted:

- `finance.get_ipo_calendar()` — when user asks "IPO"

Route by `provenance.resolver.market`: skip SEC calls when market=IDX, skip disclosures/corp-actions when market=US.

## Output Format

```
<SYM> — Catalysts

RECENT NEWS [FACT]
  · <headline> — <publisher>, <date>
  · ...

DISCLOSURES [FACT — IDX only]
  · <date> · <category> · <title>
  · ...

CORPORATE ACTIONS [FACT]
  · <date> · <kind> · <ratio/desc>
  · ...

DIVIDENDS [FACT]
  ex-date       payment       per-share    currency
  YYYY-MM-DD    YYYY-MM-DD    X.XX         IDR/USD
  ...

SEC FILINGS [FACT — US only]
  · <filed> · <form> · <primary_document link>
  · ...

INTERPRETATION [ANALYSIS]
  Material items (rank by potential price impact)
  Recurring themes (regulatory, earnings, insider, M&A)

RISKS [RISK]
  · Unresolved regulatory / litigation from disclosure
  · Insider selling density (if visible)

CONFIDENCE
  Low if: sparse news + no disclosures
  High if: multiple corroborating sources this month
```

## Rules

- Never invent a headline. If `search_news` returns empty, say "no material news this window".
- Corporate action `kind` field values are provider-normalized ("split", "rights_issue", "bonus", "dividend"); print as returned.
- Dividend amount currency comes from the tool — do NOT convert to USD unless the user asks.
- Never editorialize a headline. Print + cite; interpretation section separately.
- If the user asks "IPO calendar" without a symbol, call `get_ipo_calendar` only (no per-symbol tools).
