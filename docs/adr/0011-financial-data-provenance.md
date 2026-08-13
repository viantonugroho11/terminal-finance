# ADR-0011: Data provenance, source hierarchy, and conflict resolution

## Status

Accepted (Phase D + F landed 2026-08-13). Provenance envelope now carries
`tier` alongside `source`; tier ranking lives at
`finance_mcp/schema.py::TIER_RANK` (primary=0, aggregator=1, scraped=2,
mock=3). Skills consuming multi-source data pick the lowest-rank tier
on conflict. Multi-source `Router.call_all(...)` shipped in Phase F —
fan-out concurrent across every registered provider in the chain,
silently drops errors, returns list of `(value, provider)` pairs for
explicit cross-verification against the tier hierarchy. Extends
ADR-0004.

## Context

Phase 2 wraps every tool reply in `Provenance{source, retrieved_at,
cache_hit, symbol?}`. That answers "who returned this" and "how
fresh." It does not answer:

- Is this a primary source or an aggregator's rehash?
- If two providers disagree on Q3 revenue, which one wins and why?
- Can the user trace a computed metric (say, FCF yield) back to the
  raw inputs?

Phase 3 introduces SEC filings, DCF outputs, and multi-provider
routing. Provenance must scale to those.

## Decision

Extend `Provenance` and add a **source hierarchy** used everywhere:

```
1. PRIMARY_REGULATORY   e.g. SEC EDGAR filing (10-K, 10-Q, 8-K, Form 4, 13F)
2. PRIMARY_ISSUER       e.g. company IR press release, earnings PDF
3. STRUCTURED_DATASET   e.g. Financial Datasets (SEC-derived, normalized)
4. AGGREGATOR_MARKET    e.g. Polygon, Alpha Vantage, Finnhub
5. SCRAPED              e.g. yfinance (Yahoo)
6. NEWS                 e.g. Finnhub News, Yahoo News
7. DERIVED              e.g. Quant Engine output computed from above
```

New `Provenance` fields (additive; existing shape stays valid):

```
provenance {
  source:          "sec" | "financial_datasets" | "polygon" | ...
  provider_tier:   "primary" | "aggregator" | "scraped" | "mock"
  source_class:    "PRIMARY_REGULATORY" | ... | "DERIVED"
  retrieved_at:    ISO-8601
  cache_hit:       bool
  symbol:          str | null
  data_period:     e.g. "FY2025" | "Q2 2025" | "TTM" | null
  document_ref:    e.g. "0001045810-25-000012" (SEC accession) | null
  document_url:    str | null
  confidence:      "high" | "medium" | "low"
  inputs:          list[str]   # for DERIVED metrics: metric_ids used
}
```

**Conflict resolution rule:**

- Higher tier wins by default (PRIMARY_REGULATORY > STRUCTURED_DATASET
  > AGGREGATOR_MARKET > SCRAPED).
- If two sources are same tier and disagree by > 1%, tool returns
  BOTH values as a `DataConflict` block with each source, its value,
  its provenance, and a computed spread. Skill must surface the
  conflict; the LLM is NOT allowed to silently pick one.
- Timestamps break ties within the same tier when data is same-period
  (later `retrieved_at` wins for market data; later `filed_at` wins
  for filings).

**Derived metrics** (quant engine output, ADR-0013) carry
`source_class: DERIVED` and MUST list `inputs: [metric_id, ...]`
pointing at the raw provenance entries used, so any thesis number
traces back to a primary source.

## Alternatives Considered

- **Trust the first provider, log the rest** — silent data loss; user
  cannot audit disagreements. Rejected.
- **Let the LLM decide which source to trust** — puts safety in the
  worst place. Rejected.
- **Weighted average across providers** — hides disagreement; a
  weighted-average revenue is not a real revenue. Rejected.

## Consequences

### Positive

- Every important number in a research report is traceable to a
  primary source or explicitly labeled DERIVED with its inputs.
- Aggregator errors surface as conflicts instead of poisoning the
  thesis silently.
- Skills can require `provider_tier == "primary"` for load-bearing
  claims (e.g. "revenue growth vs prior year").

### Negative

- Provenance payloads grow (~200 bytes). Fine.
- Every provider adapter must set `source_class` + `provider_tier`
  correctly — mistakes here mislead conflict resolution.
- Conflict blocks add work for skills; they must render both sides
  cleanly.

## Rejected Alternatives

- Silent first-wins.
- LLM-adjudicated conflicts.
- Weighted-average synthesis of disagreeing sources.

## Implementation Notes

- Extend `finance_mcp/models.py::Provenance` with the new fields;
  serializer already deep-converts.
- Add `finance_mcp/provenance.py` with:
  - `SourceClass` enum + tier ordering
  - `resolve_conflict(candidates: list[Provenance & value]) -> Winner | DataConflict`
- Router (ADR-0012) is the natural place to invoke conflict
  resolution when it queries multiple providers.
- Skills gain a documented rule: if a reply contains `data_conflict`,
  surface both values and stop before drawing a conclusion.

## References

- ADR-0004 (base Provenance), ADR-0008 (multi-provider),
  ADR-0012 (router), ADR-0013 (derived metrics).
- Phase 3 spec §8.
