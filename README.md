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

| tool | purpose |
|---|---|
| `get_quote(symbol)` | live price, change, volume |
| `get_history(symbol, period, interval)` | OHLCV candles |
| `get_company(symbol)` | sector, industry, summary, market cap |
| `get_financials(symbol)` | P/E, ROE, margins, growth, D/E, FCF, beta |
| `get_technical(symbol, period)` | SMA(20/50/200), EMA20, RSI14, MACD, vol, drawdown — **deterministic** |
| `search_news(query, limit)` | recent news items |
| `get_market_overview()` | indices + crypto + commodities + DXY snapshot |
| `portfolio_add_transaction(...)` | record BUY/SELL/DIV/FEE |
| `portfolio_holdings(account?)` | positions with live prices, P&L, weights |
| `portfolio_summary(account?)` | totals: MV, cost, unrealized P&L, realized income |
| `portfolio_allocation(account?)` | sector allocation |
| `portfolio_risk(account?)` | HHI concentration, per-position vol + drawdown |
| `watchlist_{create,add,remove,list,quotes}` | watchlist CRUD + live quotes |

Technical indicators are computed in `finance_mcp/technical.py` — never asked of the LLM.

## Provider swap

`finance_mcp/providers/__init__.py` defines Protocols. Add `providers/polygon.py`, wire it in `server.py`. No changes to tools, skills, or Hermes config.

## Roadmap (spec Phases 5–10)

Deep research subagent · Alerts via Hermes cron · Morning briefing polish · Dedicated TUI. Current slice covers **Phases 1–4** (Phase 4 = portfolio + risk + watchlists on SQLite).

## Portfolio database

SQLite at `~/.hermes/finance/finance.db` (container path `/opt/data/finance/finance.db`). Schema in `finance-mcp/finance_mcp/portfolio/schema.sql`. Cost basis uses running-average method; SELL closes proportionally and moves the delta into realized P&L.

## Constraint

**Do not rebuild Hermes.** If a capability exists in Hermes (memory, cron, subagents, terminal backends, provider routing), use it — do not add a parallel implementation here.
