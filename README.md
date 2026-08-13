# Finance Terminal

Specialized finance layer on top of [Hermes Agent](https://hermes-agent.nousresearch.com/docs) by Nous Research.

**Not a Hermes fork.** Hermes runs unmodified. This repo adds:

- `finance-mcp/` — Python MCP server exposing quote/history/fundamentals/technicals/news
- `finance-skills/` — Hermes skills (11 total): `stock-analysis`, `crypto-analysis`, `market-overview`, `portfolio-analysis`, `risk-analysis`, `valuation-analysis`, `fundamental-analysis`, `technical-analysis`, `catalyst-analysis`, `peer-analysis`, `macro-context`, and the `equity-research` coordinator that composes them
- `config/` — `hermes.config.yaml` (registers the finance MCP) + `SOUL.md` (finance persona + safety rules)
- `docker/` — compose stack: `nousresearch/hermes-agent` + `finance-mcp` sidecar on shared bridge network

## Architecture

```
User
  │  "analyze NVDA"
  ▼
Hermes Agent (Docker: nousresearch/hermes-agent)
  ├── SOUL.md            → finance persona + safety
  ├── skills/            → stock-analysis, crypto-analysis, market-overview
  └── mcp_servers.finance → http://finance-mcp:7800/mcp
                              │
                              ▼
                       finance-mcp (Docker: this repo, Python + FastMCP)
                              │
                              ▼
                       Router → provider chain
                              │
                       ┌──────┼──────┬──────┬──────┐
                       ▼      ▼      ▼      ▼      ▼
                     yahoo   idx    bi    bps    ojk
                    (global) (IDX) (rate)(macro)(banking)
```

Hermes provides: agent runtime, memory, skill loader, MCP client, tool routing, cron, provider routing, CLI, terminal backends. We add: financial domain logic only.

### Indonesian market support

Market-aware routing (ADR-0020 / ADR-0021):

- `SymbolResolver` classifies each ticker into `US / IDX / GLOBAL / CRYPTO`. Known IDX 4-letter tickers (`BBCA`, `BBRI`, `TLKM`, `ASII`, `GOTO`, …) resolve to IDX without a `.JK` suffix. Full allowlist at `finance-mcp/finance_mcp/data/idx_tickers.txt` — refresh with `scripts/refresh_idx_tickers.py`.
- `Router` picks the provider per `(capability, market)`. IDX is primary for every Indonesian equity capability; Yahoo is the fallback for quote/history/company/financials/statements. Macro capabilities (BI-Rate, JISDOR, GDP, CPI, inflation, unemployment, banking SPI) route to `bi` / `bps` / `ojk` respectively.
- Provenance envelope carries `resolver.{market, country, currency, canonical_symbol, source}` and optional `attribution` (e.g. "Bank Indonesia", "OJK — Statistik Perbankan Indonesia").
- Banking-specific ratios (`net_interest_margin`, `non_performing_loan_ratio`, `capital_adequacy_ratio`, `loan_to_deposit_ratio`, `casa_ratio`, `cost_of_credit`, `loan_growth`, `deposit_growth`) are surfaced on `get_fundamentals` when the provider supplies them.

Try:
```
> analisis BBCA
> bandingkan BBCA dan BBRI
> IHSG hari ini
> berapa BI Rate sekarang
> apakah TLKM mahal
```

## Quickstart

```bash
./scripts/bootstrap.sh
docker exec -it hermes hermes chat
> analyze NVDA
> analyze BTC
> market
```

Bootstrap:
1. Copies `config/hermes.config.yaml` → `~/.hermes/config.yaml`
2. Copies `config/SOUL.md` → `~/.hermes/SOUL.md`
3. Symlinks `finance-skills/*` → `~/.hermes/skills/*`
4. `docker compose up -d --build` (Hermes gateway + finance-mcp)

## Tools exposed by finance-mcp

Market / research (every reply is `{data, provenance: {source, retrieved_at, cache_hit}}` on success or `{error: {code, message, ...}}` on failure):

| tool | purpose |
|---|---|
| `get_quote(symbol)` | live price, change, volume |
| `get_historical_prices(symbol, period, interval)` | OHLCV candles (alias: `get_history`) |
| `get_company_profile(symbol)` | sector, industry, summary, market cap (alias: `get_company`) |
| `get_fundamentals(symbol)` | P/E, ROE, margins, growth, D/E, FCF, beta (alias: `get_financials`) |
| `get_financial_statements(symbol)` | 3y annual income / balance / cashflow |
| `get_dividends(symbol)` | dividend history (ex-date, payment date, per-share amount, currency) |
| `get_corporate_actions(symbol)` | splits, rights issues, bonus shares, dividends |
| `get_sector_info(symbol)` | sector / industry (IDX-IC taxonomy for IDX) |
| `get_macro(indicator)` | Indonesian macro: `bi_rate`, `jisdor` (USD/IDR), `inflation`, `cpi`, `gdp`, `unemployment`, `banking_spi` |
| `get_foreign_flow(symbol)` | IDX foreign investor net buy/sell per day |
| `search_stocks(query, limit)` | Search IDX listed companies by name/code |
| `get_broker_activity(symbol, date?)` | IDX broker buy/sell summary per broker code |
| `get_order_book(symbol, depth)` | IDX bid/ask depth |
| `get_ipo_calendar()` | Recent + upcoming IDX new listings |
| `get_trading_calendar(year)` | IDX trading days + holidays |
| `get_disclosures(symbol, limit)` | Company disclosures / announcements filed to IDX |
| `get_board(symbol)` | Board of Commissioners + Directors |
| `get_shareholders(symbol)` | Major shareholders (name, kind, shares, %) |
| `get_subsidiaries(symbol)` | Subsidiaries with ownership % + business line |
| `get_idx_overview()` | IHSG + LQ45 + IDX sector performance |
| `get_idx_movers()` | IDX top gainers / losers / most active |
| `resolve_symbol_tool(symbol)` | diagnostics: show how the router will classify a symbol |
| `valuation_dcf(symbol, ...)` | Deterministic two-stage DCF (CAPM discount, FCF projection, Gordon terminal) |
| `valuation_sensitivity(symbol, ...)` | DCF grid over WACC × terminal-growth |
| `valuation_implied_growth(symbol, price, fcf_per_share, ...)` | Reverse-DCF: implied growth rate given market price |
| `evaluate_report(markdown, expected_symbol?)` | Score a research report against the ADR-0016 rubric (deterministic; verdict = accept/retry/low_confidence) |
| `get_sec_filings(symbol, form_type?, limit)` | SEC EDGAR filings history (10-K, 10-Q, 8-K, Form 4, 13F-HR) |
| `get_sec_facts(symbol, concept, taxonomy)` | SEC XBRL company facts (e.g. Revenues, NetIncomeLoss) |
| `get_technical(symbol, period)` | SMA(20/50/200), EMA20, RSI14, MACD, vol, drawdown — **deterministic** |
| `get_market_overview()` | S&P/NASDAQ/DOW/Russell/VIX + BTC/ETH + GOLD/OIL + DXY |
| `get_market_movers()` | top gainers / losers / most active |
| `search_news(query, limit)` | recent news items |
| `cache_stats()` | diagnostics: hits / misses / size |
| `portfolio_add_transaction(...)` | record BUY/SELL/DIV/FEE |
| `portfolio_holdings(account?)` | positions with live prices, P&L, weights |
| `portfolio_summary(account?)` | totals: MV, cost, unrealized P&L, realized income |
| `portfolio_allocation(account?)` | sector allocation |
| `portfolio_risk(account?)` | HHI concentration, per-position vol + drawdown |
| `watchlist_{create,add,remove,list,quotes}` | watchlist CRUD + live quotes |

Every market/research tool goes through: **cache → retry → provider → normalize → provenance**. Deterministic math (`finance_mcp/calc.py`, `finance_mcp/technical.py`) is never asked of the LLM.

## Data pipeline

```
Hermes tool call
      ↓
_do(tool, key, ttl, fetch)
      ↓
TTLCache.get_or_fetch  ── hit ─────────┐
      ↓ miss                            │
with_retry(fetch)                       │
  - retries TIMEOUT / RATE_LIMITED /    │
    PROVIDER_UNAVAILABLE                │
  - honors retry_after_seconds          │
  - exponential backoff + jitter        │
      ↓                                 │
Provider (yahoo | mock)                 │
  - raises FinanceError with code       │
      ↓                                 │
Normalized dataclass                    │
      ↓                                 │
Provenance{source, retrieved_at,        │
  cache_hit, symbol}.to_dict()  ←───────┘
      ↓
tool_call() logs tool + symbol + provider
      + latency_ms + cache + error
      ↓
{data, provenance}   or   {error: {...}}
```

## Provider swap

`finance_mcp/providers/__init__.py` defines Protocols with `tier`, `markets`, `capabilities`, `requires_api_key`. Add `providers/<name>.py`, register in `_build_router()` in `server.py`. The Router picks per `(capability, market)` using a preference table in `finance_mcp/router.py`. No changes to tools, skills, or Hermes config. Set `FINANCE_PROVIDER=mock` to run the entire MCP against `MockProvider` (deterministic seeded data, no network).

## Configuration

Environment overrides — all optional, all safe defaults:

| var | default | purpose |
|---|---|---|
| `FINANCE_PROVIDER` | `yahoo` | `yahoo` or `mock` |
| `FINANCE_MCP_HOST` / `_PORT` | `0.0.0.0` / `7800` | streamable-HTTP bind |
| `FINANCE_LOG_LEVEL` | `INFO` | logger level |
| `FINANCE_DB` | `/opt/data/finance/finance.db` | portfolio SQLite path |
| `FINANCE_CACHE_TTL_QUOTE` | `15` | quote TTL (seconds) |
| `FINANCE_CACHE_TTL_HISTORY` | `300` | history TTL |
| `FINANCE_CACHE_TTL_FUNDAMENTALS` | `21600` | fundamentals TTL |
| `FINANCE_CACHE_TTL_STATEMENTS` | `21600` | financial statements TTL |
| `FINANCE_CACHE_TTL_COMPANY` | `21600` | company profile TTL |
| `FINANCE_CACHE_TTL_MARKET` | `60` | market overview TTL |
| `FINANCE_CACHE_TTL_MOVERS` | `120` | movers TTL |
| `FINANCE_CACHE_TTL_NEWS` | `300` | news TTL |
| `FINANCE_CACHE_TTL_DIVIDENDS` | `86400` | dividend history TTL |
| `FINANCE_CACHE_TTL_CORP_ACTIONS` | `86400` | corporate actions TTL |
| `FINANCE_CACHE_TTL_SECTOR` | `604800` | sector info TTL |
| `FINANCE_CACHE_TTL_MACRO_DAILY` | `86400` | macro (bi_rate, jisdor) TTL |
| `FINANCE_CACHE_TTL_MACRO_MONTHLY` | `604800` | macro (cpi, gdp, unemployment, SPI) TTL |
| `FINANCE_IDX` | `on` | disable IDX provider with `off` |
| `FINANCE_BI` | `on` | disable Bank Indonesia provider with `off` |
| `FINANCE_BPS` | `on` | disable BPS provider with `off` |
| `FINANCE_OJK` | `on` | disable OJK provider with `off` |
| `FINANCE_SEC` | `on` | disable SEC EDGAR provider with `off` |
| `FINANCE_BPS_API_KEY` | — | required for live BPS calls; register at https://webapi.bps.go.id |
| `FINANCE_OJK_SPI_PATH` | — | path to JSON snapshot mirrored from https://data.ojk.go.id/SJKPublic |
| `FINANCE_SEC_USER_AGENT` | — | SEC policy — set to `"Your Name your@email"` |
| `FINANCE_ROUTING_CONFIG` | — | override path to routing YAML (defaults to `config/finance.routing.yaml`) |

Copy `.env.example` → `.env` at repo root before `./scripts/bootstrap.sh` if you want any of the credentialed providers (BPS/SEC/OJK) live inside Docker. Bootstrap symlinks it under `docker/.env` automatically.

No secrets are committed. API keys (when a provider needs them) must come from env vars only.

## Architecture decisions

Recorded in [`docs/adr/`](docs/adr/README.md).

**Phase 1–2 (Accepted, in production):**

- ADR-0001 — HTTP MCP transport over stdio
- ADR-0002 — Provider Protocol abstraction
- ADR-0003 — In-process TTL cache with single-flight
- ADR-0004 — Provenance wrapper on every tool reply
- ADR-0005 — Structured FinanceError with stable codes
- ADR-0006 — FastMCP shim for offline / Python 3.9 tests

**Phase 3 (Proposed — architectural gate before implementation):**

- ADR-0007 — Finance Hermes overall architecture (target stack)
- ADR-0008 — Multi-provider financial data with capability tags
- ADR-0009 — Finance MCP shape — gateway + specialized backends
- ADR-0010 — Canonical financial data models + schema versioning
- ADR-0011 — Data provenance, source hierarchy, conflict resolution
- ADR-0012 — Capability-based provider router
- ADR-0013 — Quantitative analysis engine (deterministic math)
- ADR-0014 — Advanced financial analyst skill decomposition
- ADR-0015 — Multi-agent financial research via Hermes subagents
- ADR-0016 — Research evaluator loop with bounded iterations
- ADR-0017 — DCF and valuation engine (deterministic)
- ADR-0018 — SEC EDGAR and primary-source integration
- ADR-0019 — Deep-research report format and rendering

**Indonesia extension (Accepted, in production):**

- ADR-0020 — Indonesian market data providers (IDX/BEI, BI, BPS, OJK)
- ADR-0021 — Market detection and symbol-based routing

Supporting: [decision matrix](docs/adr/phase-3-decision-matrix.md) · [reference analysis](docs/adr/phase-3-reference-analysis.md) · [implementation sequence](docs/adr/phase-3-implementation-sequence.md) · [Phase A findings](docs/adr/phase-a-indonesia-findings.md).

## Error codes

Every failure returns `{error: {code, message, provider, symbol, retry_after_seconds?}}`. Codes: `SYMBOL_NOT_FOUND`, `INVALID_SYMBOL`, `PROVIDER_UNAVAILABLE`, `RATE_LIMITED`, `AUTHENTICATION_FAILED`, `DATA_UNAVAILABLE`, `TIMEOUT`, `INTERNAL`. Skills react per-code (retry, apologize, degrade); they never invent fake values on error.

## Roadmap (spec Phases 5–10)

Deep research subagent · Alerts via Hermes cron · Morning briefing polish · Dedicated TUI. Current slice covers **Phases 1–4** — Phase 2 rebuild adds cache, retry, structured errors, logging, provenance, mock provider, financial statements, market movers, deterministic `calc` package.

## Portfolio database

SQLite at `~/.hermes/finance/finance.db` (container path `/opt/data/finance/finance.db`). Schema in `finance-mcp/finance_mcp/portfolio/schema.sql`. Cost basis uses running-average method; SELL closes proportionally and moves the delta into realized P&L.

## Constraint

**Do not rebuild Hermes.** If a capability exists in Hermes (memory, cron, subagents, terminal backends, provider routing), use it — do not add a parallel implementation here.
