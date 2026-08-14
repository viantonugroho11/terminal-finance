# Spec: Backtest engine sidecar (deferred)

Ref: ADR-0029.

## Status

**Deferred.** Do not build until:
- ADR-0023 (alert + digest) shipped and DAU proven.
- ≥10 distinct user backtest requests logged over 30 days.

Spec kept here to short-circuit design work when activation criteria hit.

## Goal

Run event-time-correct backtest of a Python strategy over IDX + US universes; return equity curve, per-trade log, drawdown, sharpe, sortino, hit rate.

## Success conditions

- `pytest backtest-mcp/tests/` green: no-look-ahead check, cost model, walk-forward.
- Sample strategies (SMA cross, BI-Rate-cut IHSG, mean-revert) run <30s on 10y daily.
- Result JSON schema stable + versioned.

## Deliverables

### 1. Sidecar service

Path: new repo dir `backtest-mcp/`.

- Own Dockerfile, own image.
- Shares Compose network with finance-mcp.
- Acts as MCP client of finance-mcp for OHLCV + macro.

### 2. Strategy DSL

Path: `backtest-mcp/strategies/`.

Each strategy = Python module exporting `on_bar(ctx) -> list[Order]`. `ctx` exposes:
- `ctx.symbol`, `ctx.now` (bar close ts)
- `ctx.prices(symbol, lookback=N)` — past bars only; enforced.
- `ctx.portfolio` — read-only positions.
- `ctx.macro(indicator, date)` — past releases only.

Order: `{symbol, side: buy|sell, qty, type: mkt|lmt, limit_price?}`.

### 3. Cost + slippage model

Configurable per market:
- IDX: 0.15% commission + 0.1% PPh sell + 5bps slippage.
- US: $0.005/share + 2bps slippage.
- Crypto: 0.1% + 3bps slippage.

### 4. Engine

Path: `backtest-mcp/engine.py`.

Event loop: iterate bars in ascending time; call strategy `on_bar`; simulate fills at next-bar-open (no same-bar close fills); mark-to-market; record trades.

### 5. Job store

DuckDB `jobs(id, strategy, params, universe, start, end, status, submitted_at, completed_at, result_uri)`.

### 6. MCP tools

- `submit_backtest(strategy, params, universe, start, end) -> job_id`
- `get_backtest_status(job_id) -> {status, progress}`
- `get_backtest_result(job_id) -> {equity_curve, trades, metrics}`

### 7. Skill `backtest`

Parse NL → known strategy + params, submit, poll, format equity curve + metrics.

## Out of scope v1

- Intraday tick backtest.
- Multi-strategy portfolio backtest.
- Live paper trading.

## Milestones (when activated)

1. Sidecar scaffold + Compose wiring (1d).
2. Engine + cost model + look-ahead guard (2d).
3. Job store + async API (1d).
4. Sample strategies + tests (1d).
5. Skill + docs (1d).

Total: ~6d.
