# ADR-0029: Backtest engine as separate sidecar (deferred)

- Status: Accepted with deviation (implemented in v0.3.0 as an in-process package, `finance_mcp/backtest/`, not the separate sidecar container this ADR proposed — rationale in that package's docstring)
- Date: 2026-08-14
- Deciders: Finance Terminal team

## Context

Users occasionally ask counterfactuals: "backtest beli IHSG kalau BI Rate turun 25bps", "SMA 50/200 crossover BBCA sejak 2015 return berapa". Terminal has historical prices + macro releases but no simulation engine.

Backtesting is a distinct concern:
- Event-time correctness (no look-ahead).
- Transaction cost + slippage models.
- Walk-forward analysis.
- Long-running jobs (minutes-hours).

Building inside `finance-mcp` bloats a request-response service into a job runner. Different lifecycle, different failure modes.

## Decision

Design accepted. **Implementation deferred** until (a) daily-active loop from ADR-0023 lands and (b) >10 distinct user backtest requests logged.

When built: separate service `backtest-mcp`:

1. Own container, own image. Shares Docker network with finance-mcp.
2. Reads OHLCV + macro via finance-mcp tools (as MCP client) — no duplicate provider code.
3. Strategy DSL: Python module in `strategies/`. `on_bar(context)` handler; `context` exposes portfolio, prices, macro.
4. Job store: DuckDB — `(job_id, strategy, params, universe, start, end, status, result_uri)`.
5. Async: submit → job_id, poll `get_backtest_result(job_id)` or subscribe via SSE.
6. Result: equity curve, per-trade log, drawdown, sharpe, sortino, hit rate.

## Consequences

- Positive: clean separation. Backtest crash cannot hurt live finance-mcp.
- Positive: strategies live in versioned code, not prompt — reproducible.
- Negative: new deploy surface. Justified only when demand proven.
- Negative: LLM-authored strategies risk look-ahead bias — sandbox `on_bar` gets only past+current bar, never future.
- Follow-ups (on activation): DSL doc, strategy contract test, cost/slippage default calibration for IDX + US.

## Alternatives considered

- **Backtest inside finance-mcp.** Rejected: mixes request-response with long jobs.
- **Third-party (vectorbt, backtrader).** Deferred: could embed vectorbt in the sidecar rather than build from scratch.
- **Ship now.** Rejected: no daily surface yet; risk of building unused feature.

## References

- ADR-0023 (habit loop — precondition).
- ADR-0009 (finance-mcp architecture).
