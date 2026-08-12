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
      - finance.get_company_profile
      - finance.get_fundamentals
      - finance.get_financial_statements
      - finance.get_historical_prices
      - finance.get_technical
      - finance.search_news
      - finance.get_dividends
      - finance.get_corporate_actions
      - finance.get_sector_info
      - finance.resolve_symbol_tool
---

# Stock Analysis

Structured equity analysis grounded ONLY in tool output. Never fabricate numbers, prices, ratios, or news.

## When to Use

- User says: "analyze NVDA", "what do you think about AAPL", "research TSLA", "should I look at MSFT"
- Indonesian equities: "analisis BBCA", "bagaimana TLKM", "bandingkan BBCA dan BBRI" — no `.JK` suffix needed for tickers on the IDX allowlist; user may still use `BBCA.JK` explicitly.
- Any question requiring current stock fundamentals, valuation, technicals, or news

## Market Detection

The MCP resolver auto-classifies each symbol. Every tool reply's `provenance.resolver` says which market was picked (`US`, `IDX`, `GLOBAL`, `CRYPTO`) and the canonical symbol used. If the market looks wrong, call `finance.resolve_symbol_tool(<SYM>)` to inspect, and ask the user for a suffix (e.g. `BBCA.JK`).

## Indonesian equities — extras

For IDX symbols (resolver.market == "IDX"), also call in parallel:
- `finance.get_dividends(<SYM>)` — dividend history from IDX.
- `finance.get_corporate_actions(<SYM>)` — splits, rights issues, bonus shares.
- `finance.get_sector_info(<SYM>)` — IDX-IC sector taxonomy.

For **Indonesian banks** (BBCA, BBRI, BMRI, BBNI, BRIS, BJBR, BTPS, BNGA, NISP, PNBN, MEGA, …) the `get_fundamentals` reply includes bank-specific ratios when the provider supplies them: `net_interest_margin` (NIM), `non_performing_loan_ratio` (NPL), `capital_adequacy_ratio` (CAR), `loan_to_deposit_ratio` (LDR), `casa_ratio`, `cost_of_credit`, `loan_growth`, `deposit_growth`. Surface these in a `BANKING METRICS` block instead of the generic FUNDAMENTALS block; report only the ones the tool returned (never fabricate).

Currency for IDX symbols is IDR. Display prices as `Rp X,XXX` and market cap as `Rp X,XXX T` (triliun) or `Rp X,XXX M` (miliar) rather than `$`.

## Procedure

For symbol `<SYM>`, call finance MCP tools **in parallel**:

1. `finance.get_quote(<SYM>)` — current price + change
2. `finance.get_company_profile(<SYM>)` — business overview
3. `finance.get_fundamentals(<SYM>)` — valuation ratios + margins + growth
4. `finance.get_financial_statements(<SYM>)` — 3y income / balance / cashflow
5. `finance.get_technical(<SYM>, period="1y")` — SMA/EMA/RSI/MACD/volatility/drawdown
6. `finance.search_news(<SYM>, limit=8)` — recent headlines

Every tool reply has shape `{data: ..., provenance: {source, retrieved_at, cache_hit}}`.
Use `data` for numbers; cite `provenance.source` at the end of your response.

If a reply has an `error` key instead of `data`:
- `SYMBOL_NOT_FOUND` / `INVALID_SYMBOL` → tell user the symbol is not recognized; do not fabricate.
- `RATE_LIMITED` / `PROVIDER_UNAVAILABLE` / `TIMEOUT` → apologize, suggest retry, name the code.
- `DATA_UNAVAILABLE` → say the specific field is unavailable and continue with what you have.
Never substitute training-data knowledge for a missing tool result.

Every numeric claim must trace to a tool result. If a field is null, say "not available" — do not guess.

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

SOURCES
  Quote / Fundamentals / Statements / Technicals: <provenance.source>
  News: <publisher list from search_news>
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
