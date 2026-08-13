# API Reference

All 37 finance-mcp tools. Every reply carries the envelope from [ARCHITECTURE](ARCHITECTURE.md#envelope-contract). Error codes at bottom.

- [Market data](#market-data)
- [Fundamentals + statements](#fundamentals--statements)
- [IDX microstructure + market-wide](#idx-microstructure--market-wide)
- [Macro (Indonesia)](#macro-indonesia)
- [SEC EDGAR](#sec-edgar)
- [Valuation](#valuation)
- [Technicals](#technicals)
- [News + evaluator + diagnostics](#news--evaluator--diagnostics)
- [Portfolio + watchlists](#portfolio--watchlists)
- [Error codes](#error-codes)

## Market data

### `get_quote(symbol)`

Real-time quote. Auto-detects market — no `.JK` suffix needed for allowlisted IDX tickers.

**Args:** `symbol: str` — e.g. `"NVDA"`, `"BBCA"`, `"BBCA.JK"`, `"BTC-USD"`.

**Returns:** `{symbol, price, change, change_percent, volume, currency, timestamp}`.

**Routes:** `quote` capability. IDX→[idx, yahoo]. US/GLOBAL/CRYPTO→[yahoo]. Cache 15s.

**Example:**
```json
{
  "data": {"symbol": "BBCA.JK", "price": 9500.0, "change": 100.0,
           "change_percent": 1.06, "volume": 12345000,
           "currency": "IDR", "timestamp": "2026-08-13T..."},
  "provenance": {"source": "idx", "tier": "scraped", "resolver": {...}, ...}
}
```

### `get_historical_prices(symbol, period="6mo", interval="1d")`

OHLCV history. Alias: `get_history`.

**Args:** `period ∈ {1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max}`; `interval ∈ {1d, 1wk, 1mo}`.

**Returns:** `list[{date, open, high, low, close, volume}]`.

**Cache:** 5 min.

### `get_market_overview()`

Global snapshot: S&P 500 / NASDAQ / DOW / Russell / VIX + BTC/ETH + GOLD/OIL + DXY. US-only.

For IDX equivalent see [`get_idx_overview`](#get_idx_overview).

### `get_market_movers()`

US top gainers / losers / most active from Yahoo screener.

For IDX equivalent see [`get_idx_movers`](#get_idx_movers).

## Fundamentals + statements

### `get_company_profile(symbol)`

Alias: `get_company`. Returns `{symbol, name, sector, industry, country, website, employees, summary, market_cap}`.

### `get_fundamentals(symbol)`

Alias: `get_financials`. Ratios + margins + growth + beta. **For IDX banks** (BBCA/BBRI/BMRI/…) also carries `net_interest_margin`, `non_performing_loan_ratio`, `capital_adequacy_ratio`, `loan_to_deposit_ratio`, `casa_ratio`, `cost_of_credit`, `loan_growth`, `deposit_growth` when the routed provider supplies them.

### `get_financial_statements(symbol)`

3-year annual income + balance + cashflow. Cache 6h.

### `get_dividends(symbol)`

Dividend history (ex-date, payment date, per-share amount, currency). IDX-only.

### `get_corporate_actions(symbol)`

Splits, rights issues, bonus shares, dividends. IDX-only.

### `get_sector_info(symbol)`

Sector / industry with IDX-IC taxonomy for IDX symbols.

## IDX microstructure + market-wide

All IDX-only. No fallback — outage returns `DATA_UNAVAILABLE`.

### `get_foreign_flow(symbol)`

Daily foreign investor net buy/sell (asing) for the last ~30 sessions. Cache 5 min.

**Returns:** `{symbol, days: [{date, buy_value, sell_value, net_value, currency}]}`.

### `search_stocks(query, limit=20)`

Fuzzy search IDX listed companies by name or code fragment.

**Returns:** `list[{symbol, name, sector, market}]`.

### `get_broker_activity(symbol, date?)`

Per-broker buy/sell/net for a given session (defaults to latest).

**Returns:** `{symbol, date, rows: [{broker_code, broker_name, buy_lot, sell_lot, buy_value, sell_value, net_value}]}`.

### `get_order_book(symbol, depth=10)`

Bid/ask depth. Cache 10s (near-realtime).

**Returns:** `{symbol, timestamp, bids: [{price, volume, orders?}], asks: [...]}`.

### `get_ipo_calendar()`

Recent + upcoming IDX new listings. Cache 6h. No symbol needed.

### `get_trading_calendar(year)`

IDX trading days + holidays for a calendar year. Cache 7d.

### `get_disclosures(symbol, limit=20)`

Company disclosures / announcements filed to IDX. Cache 10 min.

### `get_board(symbol)`

Board of Commissioners + Board of Directors with position + since-date. Cache 7d.

### `get_shareholders(symbol)`

Major shareholders: name, kind, shares, pct. Cache 1d.

### `get_subsidiaries(symbol)`

Subsidiaries with ownership_pct + business line. Cache 7d.

### `get_idx_overview()`

IDX-native: IHSG + LQ45 + sector performance in one call. Cache 60s. **No symbol.**

**Returns:** `{indices: [{code, value, change, change_percent, volume, value_traded, timestamp}], sectors: [{sector_code, sector_name, change_percent, value_traded}]}`.

### `get_idx_movers()`

IDX top gainers / losers / most active. Cache 2 min. **No symbol.**

## Macro (Indonesia)

### `get_macro(indicator)`

Single dispatch tool. Routes per `indicator` name to the authoritative provider.

| Indicator | Provider | Freq | Cache |
|---|---|---|---|
| `bi_rate` | bi | monthly | 1d |
| `jisdor` (alias `fx_usd_idr`) | bi | daily | 1d |
| `gdp` (alias `gdp_growth`) | bps | quarterly | 7d |
| `cpi` (alias `cpi_yoy`) | bps | monthly | 7d |
| `inflation` | bps | monthly | 7d |
| `unemployment` | bps | quarterly | 7d |
| `banking_spi` (aliases `npl`, `car`, `credit_growth`) | ojk | monthly | 7d |

**Returns:** `{indicator, source, unit, observations: [{period, value, unit}], frequency, description, attribution}`.

**Requires:** `FINANCE_BPS_API_KEY` for BPS indicators; `FINANCE_OJK_SPI_PATH` for banking_spi.

## SEC EDGAR

### `get_sec_filings(symbol, form_type?, limit=20)`

SEC EDGAR filings history. `form_type ∈ {"10-K", "10-Q", "8-K", "4", "13F-HR", ...}`.

**Returns:** `{symbol, cik, entity_name, items: [{accession_no, form, filed_date, report_date, primary_document, url}]}`.

**Requires:** `FINANCE_SEC_USER_AGENT` (SEC policy — must identify caller). Rate-limited 10 req/sec.

### `get_sec_facts(symbol, concept, taxonomy="us-gaap")`

XBRL company facts for one concept. Concepts: `Revenues`, `NetIncomeLoss`, `Assets`, `CashAndCashEquivalentsAtCarryingValue`, … see [SEC XBRL frames](https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json) for a live example.

**Returns:** `{symbol, cik, concept, taxonomy, label, description, observations: [{value, unit, period_end, period_start, form, filed_date, accession_no}]}`.

## Valuation

### `valuation_dcf(symbol, discount_rate?, terminal_growth=0.03, projection_years=5, growth_rate?)`

Deterministic two-stage DCF. Auto-assembles FCF from statements + beta from fundamentals + net_debt from balance sheet.

**Defaults:** discount_rate via CAPM (rf=4.5%, ERP=5.5%, β from provider or 1.0); growth_rate via FCF CAGR (fallback 5%).

**Returns:** `{symbol, inputs: {base_fcf, growth_rate, derived_growth_rate, projection_years, discount_rate, terminal_growth, beta_used, net_debt, market_cap}, projected_fcf, pv_explicit, terminal_value, pv_terminal, enterprise_value, equity_value, per_share_value, upside_vs_market_cap}`.

### `valuation_sensitivity(symbol, discount_rates?, terminal_growths?, projection_years=5)`

Grid of enterprise value over WACC × terminal-growth.

**Defaults:** discount_rates `[0.08, 0.09, 0.10, 0.11, 0.12]`, terminal_growths `[0.01, 0.02, 0.03, 0.04]`.

### `valuation_implied_growth(symbol, current_price_per_share, base_fcf_per_share, projection_years=5, discount_rate=0.10, terminal_growth=0.03)`

Reverse-DCF via bisection. Returns `{implied_growth: float | null, note?}` — null when price is outside the [-20%, +60%] growth band.

## Technicals

### `get_technical(symbol, period="1y")`

Deterministic: SMA(20/50/200), EMA20, RSI14, MACD, 30d annualized volatility, max drawdown. All computed in `finance_mcp.technical`, never asked of the LLM.

**Returns:** `{symbol, period, sma_20, sma_50, sma_200, ema_20, rsi_14, macd, macd_signal, macd_hist, volatility_30d_annualized_pct, max_drawdown_pct}`.

## News + evaluator + diagnostics

### `search_news(query, limit=10)`

Recent news for a symbol or query. `limit ≤ 20` practical.

**Returns:** `list[{title, publisher, link, published, summary}]`.

### `evaluate_report(markdown, expected_symbol?)`

Score a research report against the ADR-0016 rubric. Verdict: `accept` (≥80) / `retry` (60-79) / `low_confidence` (<60).

**Returns:** `{score, verdict, passes: [criterion...], misses: [{criterion, weight, detail, line?}], counters: {uncited_numeric_lines, bull_citations, bear_citations, orphan_tickers, dangling_citations, ...}}`.

### `resolve_symbol_tool(symbol)`

Diagnostics: show how `SymbolResolver` would classify a symbol without calling any provider.

**Returns:** `{symbol, resolved: {market, country, currency, canonical_symbol, source}}`.

### `cache_stats()`

Diagnostics: hits / misses / size + registered providers + routing config source + validation warnings + schema version.

## Portfolio + watchlists

### `portfolio_add_transaction(account, symbol, side, quantity, price, fee=0.0, executed_at?, currency="USD", note?)`

Record a transaction. `side ∈ {BUY, SELL, DIV, FEE, DEPOSIT, WITHDRAW}`. `executed_at` ISO-8601 or omit for now.

### `portfolio_holdings(account?)`

Current positions with live prices, unrealized P&L, weights, currency.

**Returns:** `{account, positions: [{symbol, quantity, avg_cost, cost_basis, price, market_value, unrealized_pl, unrealized_pl_pct, weight_pct, currency}]}`.

### `portfolio_summary(account?)`

Totals with **per-currency bucket** (IDR + USD kept separate).

**Returns:** `{account, positions, market_value, cost_basis, unrealized_pl, unrealized_pl_pct, realized_income, by_currency: {USD: {positions, market_value, cost_basis, unrealized_pl, unrealized_pl_pct}, IDR: {...}}, holdings}`. Top-level scalars naively sum across currencies for back-compat with 0.1.x — use `by_currency` for mixed books.

### `portfolio_allocation(account?)`

Sector allocation via company profile lookup.

### `portfolio_risk(account?)`

Herfindahl concentration + top-5 weight + per-position 30d volatility + 6mo max drawdown.

### `watchlist_create(name)` / `watchlist_add(name, symbol)` / `watchlist_remove(name, symbol)` / `watchlist_list()` / `watchlist_quotes(name)`

Standard CRUD + one-shot live-quote fanout. `watchlist_quotes` routes each symbol through the Router so mixed IDX+US watchlists just work.

## Error codes

Every failure returns `{"error": {code, message, provider, symbol?, retry_after_seconds?, details?}}`. Never a fake default.

| Code | Meaning | Retryable |
|---|---|---|
| `SYMBOL_NOT_FOUND` | Provider has no record of the symbol | no (stop-code) |
| `INVALID_SYMBOL` | Symbol failed a syntactic check (e.g. bare 3-letter for IDX) | no (stop-code) |
| `AUTHENTICATION_FAILED` | Missing/invalid credential — BPS key, SEC UA | no (stop-code) |
| `RATE_LIMITED` | Provider throttled | yes (respects `retry_after_seconds`) |
| `PROVIDER_UNAVAILABLE` | 5xx / connection / Cloudflare 403/503 | yes (with backoff) |
| `TIMEOUT` | Provider didn't respond in time | yes |
| `DATA_UNAVAILABLE` | Field/series missing from an otherwise-successful response | no |
| `INTERNAL` | Unclassified — check logs | no |

Skills MUST react per-code — never invent a value on error. See [ADR-0005](adr/0005-structured-finance-errors-with-stable-codes.md).
