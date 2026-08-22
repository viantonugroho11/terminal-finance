# Finance Terminal

[![version](https://img.shields.io/badge/version-0.3.0-blue.svg)](https://github.com/viantonugroho11/terminal-finance/releases/tag/v0.3.0)
[![CI](https://github.com/viantonugroho11/terminal-finance/actions/workflows/ci.yml/badge.svg)](https://github.com/viantonugroho11/terminal-finance/actions/workflows/ci.yml)
[![tools](https://img.shields.io/badge/mcp%20tools-82-informational.svg)]()
[![skills](https://img.shields.io/badge/skills-21-informational.svg)]()
[![providers](https://img.shields.io/badge/providers-9-informational.svg)]()
[![license](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)

Chat-driven financial research terminal. Ask in plain English or Indonesian — get quotes, fundamentals, valuations, macro data, and full equity research reports, sourced from live upstreams with provenance on every answer.

Built as a **finance layer on top of [Hermes Agent](https://hermes-agent.nousresearch.com/docs)** (Nous Research). Hermes runs unmodified; this repo only adds financial domain logic.

**Coverage:** US equities (Yahoo + SEC EDGAR) · Indonesian equities IDX/BEI · Indonesian macro (Bank Indonesia, BPS, OJK) · Crypto · Global indices/commodities.

---

## Try it in 60 seconds

```bash
./scripts/bootstrap.sh              # copies config + starts docker
docker exec -it hermes hermes chat  # open the terminal
```

Then ask:

```
> analyze NVDA                 # US equity full research
> analisis BBCA                # Indonesian bank, in Indonesian
> bandingkan BBCA dan BBRI     # peer comparison
> IHSG hari ini                # Indonesian market overview
> berapa BI Rate sekarang      # Bank Indonesia policy rate
> analyze BTC                  # crypto
> market                       # global indices snapshot
```

Every reply carries `{data, provenance: {source, retrieved_at, cache_hit}}` — you always see where the number came from.

---

## What's inside this repo

| Path | What it is |
|---|---|
| `finance-mcp/` | Python MCP server. Exposes 82 tools (quotes, fundamentals, DCF, SEC filings, IDX microstructure, macro, portfolio, watches, news, backtest, crypto/FX). Hermes calls into it over HTTP. |
| `finance-skills/` | 21 Hermes skills. Analysis: `stock-analysis`, `fundamental-analysis`, `technical-analysis`, `valuation-analysis`, `risk-analysis`, `catalyst-analysis`, `peer-analysis`, `macro-context`, `market-overview`. Indonesia + flow: `flow-analysis`. Crypto + FX: `crypto-analysis`, `crypto-deep`, `fx-analysis`. Portfolio: `portfolio-analysis`, `portfolio-rebalance`. Daily loop: `watch`, `morning-digest`, `news-brief`. Research: `backtest`, `screener`, and the `equity-research` coordinator that composes the rest. |
| `config/` | `hermes.config.yaml` (registers the finance MCP) + `SOUL.md` (persona + safety rules). |
| `docker/` | Compose stack: `nousresearch/hermes-agent` + `finance-mcp` sidecar on a shared network. |
| `docs/` | Architecture, API, provider notes, runbooks, ADRs. |

Hermes gives us: agent runtime, memory, skill loader, MCP client, cron, CLI, terminal backends. We add: financial domain logic only. **No Hermes fork.**

---

## How it works

```
User
  │  "analyze NVDA"
  ▼
Hermes Agent (Docker)
  ├── SOUL.md            → persona + safety
  ├── skills/            → picks the right analysis skill(s)
  └── mcp_servers.finance → http://finance-mcp:7800/mcp
                              │
                              ▼
                       finance-mcp (Python + FastMCP)
                              │
                       Router picks provider per (capability, market)
                              │
             ┌────────┬───────┼───────┬───────┬───────┐
             ▼        ▼       ▼       ▼       ▼       ▼
           yahoo    idx     bi      bps     ojk     sec
          (global) (IDX)  (rate)  (macro) (bank) (filings)
```

Every tool call goes through: **cache → retry → provider → normalize → provenance**. Deterministic math (DCF, ratios, technicals) lives in `finance_mcp/calc.py` + `technical.py` — never asked of the LLM.

### Indonesian market routing

`SymbolResolver` classifies each ticker as `US / IDX / GLOBAL / CRYPTO`. Known 4-letter IDX tickers (`BBCA`, `BBRI`, `TLKM`, `ASII`, `GOTO`, …) resolve without a `.JK` suffix. Full allowlist in `finance-mcp/finance_mcp/data/idx_tickers.txt` (refresh via `scripts/refresh_idx_tickers.py`).

`Router` then picks the provider per `(capability, market)`. IDX is primary for Indonesian equity capabilities; Yahoo is fallback. Macro routes to `bi` (rates/FX), `bps` (GDP/CPI/inflation/unemployment), `ojk` (banking SPI).

Banking-specific ratios (NIM, NPL, CAR, LDR, CASA, cost of credit, loan/deposit growth) appear on `get_fundamentals` when the provider supplies them.

---

## Tools exposed by finance-mcp

<details>
<summary><b>Market data & research</b> (click to expand)</summary>

| tool | purpose |
|---|---|
| `get_quote(symbol)` | live price, change, volume |
| `get_historical_prices(symbol, period, interval)` | OHLCV candles (alias: `get_history`) |
| `get_company_profile(symbol)` | sector, industry, summary, market cap (alias: `get_company`) |
| `get_fundamentals(symbol)` | P/E, ROE, margins, growth, D/E, FCF, beta (alias: `get_financials`) |
| `get_financial_statements(symbol)` | 3y annual income / balance / cashflow |
| `get_dividends(symbol)` | dividend history |
| `get_corporate_actions(symbol)` | splits, rights issues, bonus shares, dividends |
| `get_sector_info(symbol)` | sector / industry (IDX-IC taxonomy for IDX) |
| `get_technical(symbol, period)` | SMA(20/50/200), EMA20, RSI14, MACD, vol, drawdown — deterministic |
| `search_news(query, limit)` | recent news items |
| `get_market_overview()` | S&P/NASDAQ/DOW/Russell/VIX + BTC/ETH + GOLD/OIL + DXY |
| `get_market_movers()` | top gainers / losers / most active |

</details>

<details>
<summary><b>Indonesia (IDX / BI / BPS / OJK)</b></summary>

| tool | purpose |
|---|---|
| `get_macro(indicator)` | `bi_rate`, `jisdor` (USD/IDR), `inflation`, `cpi`, `gdp`, `unemployment`, `banking_spi` |
| `get_foreign_flow(symbol)` | IDX foreign investor net buy/sell per day |
| `search_stocks(query, limit)` | search IDX listed companies |
| `get_broker_activity(symbol, date?)` | IDX broker buy/sell summary |
| `get_order_book(symbol, depth)` | IDX bid/ask depth |
| `get_ipo_calendar()` | recent + upcoming IDX listings |
| `get_trading_calendar(year)` | IDX trading days + holidays |
| `get_disclosures(symbol, limit)` | company announcements filed to IDX |
| `get_board(symbol)` | Board of Commissioners + Directors |
| `get_shareholders(symbol)` | major shareholders |
| `get_subsidiaries(symbol)` | subsidiaries with ownership % + business line |
| `get_idx_overview()` | IHSG + LQ45 + IDX sector performance |
| `get_idx_movers()` | IDX top gainers / losers / most active |

</details>

<details>
<summary><b>Valuation & US primary sources</b></summary>

| tool | purpose |
|---|---|
| `valuation_dcf(symbol, ...)` | two-stage DCF (CAPM discount, FCF projection, Gordon terminal) |
| `valuation_sensitivity(symbol, ...)` | DCF grid over WACC × terminal-growth |
| `valuation_implied_growth(symbol, price, fcf_per_share, ...)` | reverse-DCF |
| `get_sec_filings(symbol, form_type?, limit)` | SEC EDGAR filings (10-K, 10-Q, 8-K, Form 4, 13F-HR) |
| `get_sec_facts(symbol, concept, taxonomy)` | SEC XBRL company facts |
| `evaluate_report(markdown, expected_symbol?)` | score research report vs ADR-0016 rubric |

</details>

<details>
<summary><b>Portfolio & watchlist</b></summary>

| tool | purpose |
|---|---|
| `portfolio_add_transaction(...)` | record BUY/SELL/DIV/FEE |
| `portfolio_holdings(account?)` | positions with live prices, P&L, weights |
| `portfolio_summary(account?)` | totals: MV, cost, unrealized P&L, realized income |
| `portfolio_allocation(account?)` | sector allocation |
| `portfolio_risk(account?)` | HHI concentration, per-position vol + drawdown |
| `watchlist_{create,add,remove,list,quotes}` | watchlist CRUD + live quotes |

SQLite at `~/.hermes/finance/finance.db` (container: `/opt/data/finance/finance.db`). Schema at `finance-mcp/finance_mcp/portfolio/schema.sql`. Cost basis: running-average; SELL closes proportionally, delta into realized P&L.

</details>

<details>
<summary><b>Diagnostics</b></summary>

| tool | purpose |
|---|---|
| `resolve_symbol_tool(symbol)` | show how the router will classify a symbol |
| `cache_stats()` | hits / misses / size, routing warnings |

</details>

---

## Configuration

All environment variables are optional with safe defaults. Copy `.env.example` → `.env` at the repo root before `./scripts/bootstrap.sh` if you want credentialed providers (BPS/SEC/OJK) live inside Docker — bootstrap symlinks it under `docker/.env` automatically. **No secrets are committed.**

<details>
<summary><b>Full env var reference</b></summary>

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
| `FINANCE_IDX` / `_BI` / `_BPS` / `_OJK` / `_SEC` | `on` | set to `off` to skip that provider at startup |
| `FINANCE_BPS_API_KEY` | — | required for live BPS calls — register at https://webapi.bps.go.id |
| `FINANCE_OJK_SPI_PATH` | — | path to JSON snapshot mirrored from https://data.ojk.go.id/SJKPublic |
| `FINANCE_SEC_USER_AGENT` | — | SEC policy — set to `"Your Name your@email"` |
| `FINANCE_ROUTING_CONFIG` | — | override routing YAML path (default: `config/finance.routing.yaml`) |

</details>

### Adding a provider

`finance_mcp/providers/__init__.py` defines Protocols with `tier`, `markets`, `capabilities`, `requires_api_key`. Add `providers/<name>.py`, register in `_build_router()` in `server.py`. Router picks per `(capability, market)` from `finance_mcp/router.py`. **No changes needed to tools, skills, or Hermes config.** Set `FINANCE_PROVIDER=mock` to run the whole MCP against `MockProvider` (deterministic seeded data, no network).

### Error contract

Every failure returns `{error: {code, message, provider, symbol, retry_after_seconds?}}`.

Codes: `SYMBOL_NOT_FOUND`, `INVALID_SYMBOL`, `PROVIDER_UNAVAILABLE`, `RATE_LIMITED`, `AUTHENTICATION_FAILED`, `DATA_UNAVAILABLE`, `TIMEOUT`, `INTERNAL`, `SCREENER_FIELD_UNKNOWN`.

Skills react per-code (retry, apologize, degrade) — they **never invent fake values on error**.

---

## Deep docs

- [ARCHITECTURE](docs/ARCHITECTURE.md) — data flow, module map, design decisions, failure modes
- [API](docs/API.md) — every tool with request/response examples
- [PROVIDERS](docs/PROVIDERS.md) — per-upstream: endpoints, auth, failure modes
- [RUNBOOKS](docs/RUNBOOKS.md) — refresh allowlist, add provider, debug failure, cut release
- [CONTRIBUTING](docs/CONTRIBUTING.md) — env setup, test flow, PR checklist
- [CHANGELOG](CHANGELOG.md) — release history
- [ADRs](docs/adr/README.md) — 31 records: 27 accepted (1 bridged, 1 with deviation), 3 proposed-only

---

## Roadmap

**Shipped (v0.2.0, 2026-08-13):**
- Phases 1–2 baseline: cache, retry, structured errors, provenance, mock provider, statements, movers, deterministic `calc`
- Phase A/B: Indonesia — `SymbolResolver` + market-aware Router + `IdxProvider`
- Phase C: macro — Bank Indonesia (BI-Rate, JISDOR) + BPS (GDP/CPI/inflation/unemployment) + OJK (banking SPI)
- Phase D: 12 IDX microstructure capabilities + YAML routing + tier hierarchy + schema versioning
- Phase E: DCF/valuation engine (CAPM/WACC/Gordon/sensitivity/reverse-DCF) + SEC EDGAR (filings + XBRL) + canonical report format
- Phase F Steps 1–2: six specialist analyst skills + `equity-research` coordinator + deterministic evaluator loop + in-process subagent fan-out shim

**Shipped (v0.3.0, 2026-08-14):**
- Daily habit loop: alert engine + Telegram delivery + pre-open morning digest (ADR-0023)
- News + sentiment layer: RSS ingest, symbol tagger, sentiment scoring (ADR-0028)
- IDX flow deep-dive: insider trades, major-holder changes, KSEI ownership (ADR-0026)
- Lot-tracked portfolio with Indonesian tax + rebalance (ADR-0027)
- Deterministic backtest engine, in-process (ADR-0029)
- Crypto + forex expansion: multi-venue, derivatives, JISDOR + CIP forwards (ADR-0031)

**Ahead — blocked on Hermes-side runtime:**
- Native Hermes subagent spawn for true parallel research (ADR-0015 native tier)
- LLM-adjudicated evaluator retry loop (ADR-0016 LLM tier)

**Ahead — specced, not built:**
- IDX earnings transcript Q&A (ADR-0024) — needs per-issuer IR scrapers plus a PDF/embedding stack; feasibility unproven
- Multi-tenant hosted mode (ADR-0030) — needs a tenant key in the data layer first

**Ahead — in-repo:**
- Dedicated TUI

---

## Development

```bash
cd finance-mcp
pip install -e ".[dev]"
pytest            # 305 tests, fully offline — no upstream is contacted
ruff check .      # same gate CI enforces
```

Runtime targets Python 3.12 (see `finance-mcp/Dockerfile`); 3.11 is the declared
floor and both are covered by CI. The test suite additionally runs on 3.9 via the
FastMCP shim (ADR-0006) for offline local work.

---

## License

[GNU AGPL-3.0](LICENSE). Use, modify, and self-host freely.

The one obligation worth knowing up front: **§13 — if you run a modified
version of this over a network, you must offer its source to the users of
that service.** Running it unmodified for yourself, or on a private box for
people you know, triggers nothing. Publishing a modified hosted service does.

Market data itself is *not* covered by this license — each upstream carries
its own terms, and some restrict redistribution (IDX in particular). See
[PROVIDERS](docs/PROVIDERS.md) before republishing any dataset.

---

## Constraint

**Do not rebuild Hermes.** If a capability exists in Hermes (memory, cron, subagents, terminal backends, provider routing), use it — do not add a parallel implementation here.
