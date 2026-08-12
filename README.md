# Finance Terminal

Specialized finance layer on top of [Hermes Agent](https://hermes-agent.nousresearch.com/docs) by Nous Research.

**Not a Hermes fork.** Hermes runs unmodified. This repo adds:

- `finance-mcp/` — Python MCP server exposing quote/history/fundamentals/technicals/news
- `finance-skills/` — Hermes skills (`stock-analysis`, `crypto-analysis`, `market-overview`) that orchestrate the MCP tools
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
                       providers/yahoo.py   (yfinance — swap for Polygon/AlphaVantage later)
```

Hermes provides: agent runtime, memory, skill loader, MCP client, tool routing, cron, provider routing, CLI, terminal backends. We add: financial domain logic only.

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

`finance_mcp/providers/__init__.py` defines Protocols. Add `providers/polygon.py`, register in `_pick_provider()` in `server.py`. No changes to tools, skills, or Hermes config. Set `FINANCE_PROVIDER=mock` to run the entire MCP against `MockProvider` (deterministic seeded data, no network).

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

Supporting: [decision matrix](docs/adr/phase-3-decision-matrix.md) · [reference analysis](docs/adr/phase-3-reference-analysis.md) · [implementation sequence](docs/adr/phase-3-implementation-sequence.md).

## Error codes

Every failure returns `{error: {code, message, provider, symbol, retry_after_seconds?}}`. Codes: `SYMBOL_NOT_FOUND`, `INVALID_SYMBOL`, `PROVIDER_UNAVAILABLE`, `RATE_LIMITED`, `AUTHENTICATION_FAILED`, `DATA_UNAVAILABLE`, `TIMEOUT`, `INTERNAL`. Skills react per-code (retry, apologize, degrade); they never invent fake values on error.

## Roadmap (spec Phases 5–10)

Deep research subagent · Alerts via Hermes cron · Morning briefing polish · Dedicated TUI. Current slice covers **Phases 1–4** — Phase 2 rebuild adds cache, retry, structured errors, logging, provenance, mock provider, financial statements, market movers, deterministic `calc` package.

## Portfolio database

SQLite at `~/.hermes/finance/finance.db` (container path `/opt/data/finance/finance.db`). Schema in `finance-mcp/finance_mcp/portfolio/schema.sql`. Cost basis uses running-average method; SELL closes proportionally and moves the delta into realized P&L.

## Constraint

**Do not rebuild Hermes.** If a capability exists in Hermes (memory, cron, subagents, terminal backends, provider routing), use it — do not add a parallel implementation here.
