# ADR-0025: Conversational equity screener (IDX + US)

- Status: Proposed
- Date: 2026-08-14
- Deciders: Finance Terminal team

## Context

Users ask "cari bank IDX PBV<1.5, ROE>15%, div yield>5%" or "US semis market cap >100B, FCF yield >4%". Current terminal answers single-symbol queries only. Yahoo screener covers US; IDX has no equivalent open API.

Real-time scan across full universe (700+ IDX, 8000+ US) too slow via per-symbol tool calls. Need precomputed snapshot.

## Decision

Add nightly snapshot pipeline + `screener` skill:

1. Cron `0 22 * * 1-5` (post-close both markets) walks ticker universes, calls `get_fundamentals` + `get_quote` per symbol via existing router. Persists to `screener_snapshot.duckdb` (columnar, fast filter).
2. New MCP tool `screen_stocks(filters: list[Filter], market, order_by, limit)` runs SQL over snapshot. `Filter = {field, op, value}` with allowlisted fields (pe, pbv, roe, div_yield, mcap, sector, fcf_yield, ...).
3. New skill `screener` translates NL query → filter list (DeepSeek), echoes parsed filters for confirmation, calls tool, ranks + explains.

DuckDB chosen over SQLite: columnar scan on 8k rows × 40 cols in <50ms; zero-config; single file.

## Consequences

- Positive: reuses every existing provider tool. No new upstream.
- Positive: snapshot freshness is transparent (`snapshot_date` in provenance) — user knows results are T-1.
- Negative: nightly job long (~30min for 8k tickers with rate limits). Mitigation: incremental — refresh only tickers with stale data; parallel workers per provider.
- Negative: intraday screens stale until close. Acceptable — screening is a research task, not trading.
- Negative: field allowlist must stay in sync with provider fundamentals schema. Contract test enforced.
- Follow-ups: coverage report per universe, snapshot compaction (keep 30 days), migration script when adding a new field.

## Alternatives considered

- **Live scan on demand.** Rejected: 8k tool calls per query blows rate limits + cost.
- **Third-party screener API (finviz, Simply Wall St).** Rejected: paid, closed data, no IDX.
- **Postgres.** Rejected: DuckDB embedded matches single-tenant + read-heavy workload.
- **Elasticsearch.** Rejected: overkill for structured numeric filters.

## References

- ADR-0012 (router).
- ADR-0020 (Indonesian providers).
- ADR-0022 (IDX capabilities).
