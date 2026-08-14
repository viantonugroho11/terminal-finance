# Spec: IDX flow deep-dive — insider + institutional

Ref: ADR-0026.

## Goal

Answer "broker apa net beli BBRI 5 hari terakhir", "ada insider ASII bulan ini", "% asing di BBCA sekarang".

## Success conditions

- `pytest finance-mcp/tests/test_idx_flow.py` green: aggregate correctness, KSEI parse, insider dedup.
- 4 new tools return provenance with IDX/KSEI publication date.

## Deliverables

### 1. Provider extension

Path: `finance-mcp/finance_mcp/providers/idx.py` — add methods:
- `insider_trades(symbol, days=30) -> list[InsiderTrade]`
- `major_holder_changes(symbol, days=30) -> list[HolderChange]`
- `broker_flow_agg(symbol, days=5) -> list[BrokerAggRow]`

Data source: IDX `Disclosure/AnnouncementStock` HTML + JSON endpoints. Cache TTL per ADR-0026 table.

### 2. New provider `KseiProvider`

Path: `finance-mcp/finance_mcp/providers/ksei.py`.

Method: `ownership_breakdown(symbol) -> {foreign_pct, domestic_pct, local_institutional_pct, retail_pct, as_of: date}`.

Source: KSEI Holding Composition Report (HTML scrape; snapshot cached).

### 3. MCP tools

- `get_insider_trades(symbol, days=30)`
- `get_major_holder_changes(symbol, days=30)`
- `get_ownership_breakdown(symbol)`
- `get_broker_flow_aggregate(symbol, days=5)`

### 4. Skill `flow-analysis`

Path: `finance-skills/flow-analysis/SKILL.md`.

Composes: foreign_flow (d1) + broker_flow_aggregate (d5) + insider_trades (d30) + ownership_breakdown → single narrative "smart money view" per symbol.

### 5. Precompute

Off-hours cron aggregates `broker_activity` into daily rollup to avoid N-day fanout at query time.

## Out of scope

- Real-time L2 order book (existing `get_order_book` covers).
- Non-IDX flow.

## Milestones

1. IDX disclosure scraper + models + tests (1d).
2. KSEI ownership scraper + snapshot fallback (1d).
3. Broker aggregation + precompute cron (0.5d).
4. Tools + provenance + router entries (0.5d).
5. `flow-analysis` skill + tests (1d).

Total: ~4d.
