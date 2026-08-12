# ADR-0010: Canonical financial data models + schema versioning

## Status

Proposed — Phase 3. Extends ADR-0002.

## Context

Phase 2 introduced normalized dataclasses for `Quote`, `Candle`,
`Company`, `Financials`, `NewsItem`, `IncomeStatement`, `BalanceSheet`,
`CashFlowStatement`, `FinancialStatements`, `MarketOverview`,
`MarketMovers`. They cover today's providers but were shaped by Yahoo
availability, not by what analysts actually need.

Phase 3 adds primary-source data (SEC filings, Form 4, 13F), analyst
outputs (metrics, valuations), and news with entity tagging. Provider
responses diverge on units (dividend yield: fraction vs percent),
periods (fiscal vs calendar), currencies, and null semantics.

We also need to change models over time without breaking either
skills (SKILL.md instructions cite field names) or cached data.

## Decision

We will formalize a **canonical model layer** with the following
rules:

1. Every provider adapter returns canonical models only. Provider
   dicts stop at the adapter boundary. No `map[str, Any]` in core
   models — spec §10.
2. Model file (`finance_mcp/models.py`) gains explicit new models for
   Phase 3:
   - `Filing`  (SEC document: accession, form, filed_at, period_of_report, url, extracted_facts)
   - `InsiderTrade` (Form 4: filer, symbol, side, quantity, price, filed_at)
   - `Institutional` (13F: holder, symbol, shares, value, as_of)
   - `Metric` (deterministic computed metric: name, value, unit, period, formula, inputs, source_metric_ids)
   - `Valuation` (DCF output: fair_value, method, assumptions, scenarios)
   - `AnalystNote` (structured analyst output: section, tag, claim, evidence_ids)
3. Units and currency are explicit on every numeric field
   (`unit: str`, `currency: str | None`). Never assume USD.
4. Periods use ISO date + `PeriodKind` enum (`FY`, `Q1`..`Q4`, `TTM`,
   `SPOT`) — never bare strings like `"2025"`.
5. **Schema versioning:** each model file exposes `SCHEMA_VERSION`
   (semver). Cache keys embed the schema version so a bump forces
   revalidation. Breaking changes require an ADR that names the
   migration and lists dependent skills to update.
6. `_deep_asdict` remains the single serialization path
   (JSON-safe, provenance-friendly, cache-key-friendly).

## Alternatives Considered

- **Return provider dicts directly** — leaks vendor idioms into
  skills; forbidden by spec §10. Rejected.
- **JSON Schema / Pydantic v2 with runtime validation** — attractive;
  defer to a future ADR when a real bug motivates the runtime cost.
  Dataclasses + tests + adapter contract fixtures cover us today.
- **One model per provider, mapped at the tool boundary** — pushes
  the coupling one level up; every tool becomes an if/else of
  provider shape. Rejected.

## Consequences

### Positive

- Skills reference stable field names, not provider quirks. SKILL.md
  instructions do not rot when we swap Yahoo for Polygon.
- Deterministic quant engine (ADR-0013) can rely on unit-safe inputs.
- Schema version in cache keys prevents "old shape served under new
  contract" bugs.

### Negative

- Adding a provider means writing an adapter that normalizes units,
  periods, and null semantics — real work per provider.
- `SCHEMA_VERSION` discipline required in code review; a silent
  breaking change without a bump = poisoned cache.

## Rejected Alternatives

- Passing through provider responses.
- Per-provider models.
- Runtime schema validation as the primary safety net.

## Implementation Notes

- Add `finance_mcp/models.py::SCHEMA_VERSION = "1.0.0"` and include
  it in `TTLCache` key tuples (small refactor).
- New Phase 3 models added as separate dataclasses; existing ones
  unchanged in Phase 3 unless a real gap forces it (each breaking
  change gets its own ADR).
- Contract tests: `tests/fixtures/<provider>/*.json` recorded once
  per adapter; adapter test asserts fixture → canonical model shape
  is stable.

## References

- ADR-0002 (Protocol abstraction), ADR-0011 (provenance),
  ADR-0013 (quant engine).
- Phase 2 spec §10.
