# ADR-0027: Portfolio optimizer + Indonesian tax-lot accounting

- Status: Accepted (implemented in v0.3.0 — `finance_mcp/portfolio/`)
- Date: 2026-08-14
- Deciders: Finance Terminal team

## Context

Terminal has `portfolio-analysis` skill: reads holdings, reports value + return + attribution. Missing:

- **Rebalance suggestion.** "Given target 40% equity / 30% bond / 20% cash / 10% crypto and current drift, what to trade?"
- **Indonesian tax-aware sizing.** Sell trigger 0.1% final PPh on gross proceeds (IDX). Dividend 10% final. USDT/crypto: PPh 22 0.11% + PPN. Ignoring these overstates after-tax return.
- **Tax-lot tracking.** FIFO/LIFO/HIFO per lot for cost-basis; matters for capital-gains reporting even when Indonesian PPh is final (US brokerage holdings still need cost-basis).

Current portfolio store is a flat holdings JSON — no lots, no tax awareness.

## Decision

Extend portfolio store to lot-level. Add:

1. `~/.hermes/finance/portfolio/lots.jsonl` — one line per buy: `{lot_id, symbol, qty, price, currency, fee, tax, acquired_at, account, notes}`.
2. Sells recorded as separate lines with `close_lot_id` pointing at buy lot (partial fills allowed via qty split).
3. Deterministic calc module `finance_mcp/portfolio.py` — cost-basis (FIFO/HIFO), unrealized/realized PnL, after-tax return per Indonesian regime.
4. New MCP tools: `record_trade`, `list_lots`, `unrealized_pnl`, `realized_pnl`, `rebalance_plan(targets)`.
5. `rebalance_plan` uses convex optimization (`scipy.optimize.minimize`) — minimize trade count + tax drag subject to target weights ±tolerance.
6. Skill `portfolio-rebalance` composes: read targets, compute plan, explain trades, warn tax cost per sell.

## Consequences

- Positive: honest after-tax returns for Indonesian users. Bloomberg/Yahoo assume US tax regime.
- Positive: JSONL append-only — auditable ledger, no destructive edits.
- Negative: schema migration for existing portfolio users (one-time). Provide `migrate_portfolio_v1_to_v2.py`.
- Negative: multi-currency (USD holdings + IDR base) needs FX at trade time — depends on ADR-0031 forex historical rates.
- Negative: rebalance optimization is deterministic but LLM must not mutate the plan; skill quotes plan verbatim.
- Follow-ups: tax regime pluggable (regime = 'ID' default, 'US' optional); contract test on FIFO/HIFO; runbook for corp actions (split, bonus share).

## Alternatives considered

- **Keep flat holdings.** Rejected: cannot compute realized gain accurately without lots.
- **SQLite.** Rejected: JSONL sufficient <10k trades/user; grep-friendly.
- **External portfolio tool (Ghostfolio, Beancount).** Rejected: no Indonesian tax rules; integration surface > building it here.
- **Full MPT / Black-Litterman optimizer.** Deferred: rebalance-to-target is 90% of user need; MPT belongs in separate ADR if requested.

## References

- ADR-0013 (quantitative engine).
- ADR-0031 (crypto + forex) — dependency for FX at trade time.
