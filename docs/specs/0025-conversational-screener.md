# Spec: Conversational equity screener

Ref: ADR-0025.

## Goal

"cari bank IDX PBV<1.5, ROE>15%, div yield>5%" returns ranked list with numbers + snapshot date.

## Success conditions

- `pytest finance-mcp/tests/test_screener.py` green: filter parse, SQL translation, allowlist enforcement.
- Snapshot job completes <60min for full IDX+US universe.
- Screener query returns <200ms on warm snapshot.

## Deliverables

### 1. Snapshot pipeline

Path: `finance-mcp/finance_mcp/ingest/screener_snapshot.py`.

Cron: `0 22 * * 1-5`.

Steps:
1. Load ticker universe: `data/idx_tickers.txt` + `data/us_sp500.txt`.
2. Parallel workers (4/provider) fetch `get_fundamentals` + `get_quote`.
3. Write to `~/.hermes/finance/screener_snapshot.duckdb`, table `snapshot(symbol, market, sector, industry, pe, pbv, roe, div_yield, mcap, fcf_yield, beta, revenue_growth_yoy, ..., snapshot_date)`.
4. Retain 30 days; older partitions dropped.

Incremental: skip symbols already refreshed within 20h.

### 2. MCP tool

`screen_stocks(filters: list[Filter], market: str = "ALL", order_by: str = "mcap", desc: bool = True, limit: int = 50) -> list[Row]`

`Filter = {field: str, op: "<"|"<="|">"|">="|"="|"in", value: any}`

Field allowlist declared in `finance_mcp/screener_fields.py`. Unknown field → structured error `SCREENER_FIELD_UNKNOWN` (ADR-0005).

SQL built via parameterized query — no string interpolation from LLM input.

### 3. Skill `screener`

Path: `finance-skills/screener/SKILL.md`.

Flow:
1. Parse NL → filter list (DeepSeek few-shot).
2. Echo parsed filters + confirm.
3. Call `screen_stocks`.
4. Format table + explain top 3.

### 4. Contract test

`tests/test_screener_fields_contract.py` asserts every allowlisted field is present in `get_fundamentals` output for a sample symbol.

## Out of scope

- Intraday screening.
- Custom user-defined derived fields.

## Milestones

1. DuckDB schema + snapshot writer + tests (1d).
2. Parallel refresh worker + rate limit + resume-on-failure (1d).
3. `screen_stocks` tool + allowlist + SQL builder (1d).
4. Skill NL parsing + confirmation + explain (1d).
5. Full universe cold-run + tune (0.5d).

Total: ~4.5d.
