---
name: backtest
description: Historical backtest of named strategies (SMA cross, mean revert, buy&hold) with deterministic cost + slippage + tax. Use when user says "backtest", "uji strategi", "simulasi".
version: 0.1.0
author: Finance Hermes
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, Backtest, Strategy]
    related_skills: [technical-analysis, portfolio-rebalance, market-overview]
    requires_tools:
      - finance.list_strategies
      - finance.submit_backtest
      - finance.get_backtest_status
      - finance.get_backtest_result
---

# Backtest

Deterministic bar-by-bar simulation on top of the router's OHLCV. No
look-ahead — the engine enforces it via BarContext. Sync execution
in v1; long jobs still block the call.

## When to Use

- "backtest SMA cross 20/50 BBCA sejak 2023"
- "buy and hold BBRI 3 tahun return berapa"
- "uji mean revert TLKM 2022-2025"

## Flow

1. Enumerate strategies via `finance.list_strategies()` when user is
   vague; otherwise map their words to a known name.
2. Ask user to confirm: **strategy, symbol, start, end, params**.
3. `finance.submit_backtest(strategy, symbol, start, end, params={...})`
   returns `{id, status}`.
4. `finance.get_backtest_result(id)` returns:
   - `equity_curve` (list of floats, one per bar)
   - `trades` (list of fills with pnl per SELL)
   - `metrics` (final equity, total_return, max_drawdown, sharpe,
     sortino, hit_rate, trades_count)
5. Present metrics + last 5 trades. Offer to try alternate params.

## Rules

- NEVER modify strategy parameters silently. Echo params user gave.
- Metrics are computed from equity_curve — do not invent them.
- If `sharpe` is null (variance = 0 or < 2 returns), say so, not "0".
- Do NOT extrapolate future performance from past backtest.
- Costs are baked in: 0.15% comm + 0.1% PPh sell (ID); 5bps slippage.
  Do NOT invent additional fees or discount them.
