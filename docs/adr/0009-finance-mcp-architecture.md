# ADR-0009: Finance MCP shape — gateway + specialized backends

## Status

Accepted (Phase E landed 2026-08-13). finance-mcp is a single gateway
process; specialized upstreams are provider adapters inside the same
process (not sub-MCPs). Router owns capability selection. This shape
is stable and reflected in README §Architecture.

## Context

Phase 1 shipped one `finance-mcp` process exposing all tools. Phase 3
adds SEC filings, DCF valuation, quantitative analytics, and news
intelligence. Three plausible shapes:

- **A. One large Finance MCP** — everything stays in one process.
- **B. N specialized MCPs registered directly with Hermes** — Market
  MCP, Fundamentals MCP, SEC MCP, News MCP, Crypto MCP, Quant MCP,
  each registered separately in Hermes config.
- **C. One Finance MCP gateway that internally aggregates specialized
  backends** — Hermes sees one MCP; the gateway multiplexes.

Load-bearing constraints:

1. Provenance and error semantics MUST be consistent across every
   tool reply (ADR-0004, ADR-0005) — Hermes and skills should not
   have to know which backend produced a value.
2. Provider routing (ADR-0012) needs to see the full request context
   to pick the right backend; splitting across N MCPs hides context.
3. Skills already reference `finance.*` tools; a hard split
   (`market.get_quote`, `sec.get_filing`) is a breaking rename.
4. Ops footprint matters — we deploy on one Docker host today.

## Decision

We will adopt **Option C — one Finance MCP gateway** with internal
specialized subsystems. Hermes registers a single MCP
(`mcp_servers.finance`) exposing the `finance.*` namespace. Internally
the gateway routes to subsystem packages:

```
finance-mcp/
└── finance_mcp/
    ├── server.py                       # FastMCP tools (thin)
    ├── router.py                       # capability-based dispatch (ADR-0012)
    ├── models.py                       # canonical models (ADR-0010)
    ├── provenance.py                   # source hierarchy + citation (ADR-0011)
    ├── quant/                          # deterministic engine (ADR-0013)
    ├── valuation/                      # DCF + scenarios (ADR-0017)
    ├── research/                       # orchestrator plumbing (ADR-0015)
    ├── providers/
    │   ├── market/  (yahoo, polygon, twelvedata, alphavantage)
    │   ├── fundamentals/ (financial_datasets, fmp, alphavantage)
    │   ├── news/    (finnhub, yahoo_news)
    │   ├── sec/     (edgar)
    │   └── crypto/  (coingecko)
    └── subsystems/                     # optional split later if needed
```

Subsystems are Python packages, not separate processes. If a subsystem
grows enough deps to justify a process split (e.g. heavy PDF parsing
for filings), it can extract into its own container behind an internal
HTTP interface without changing the outward MCP surface. That
promotion is a future ADR, not a Phase 3 decision.

## Alternatives Considered

- **A. Monolith, no internal boundaries** — where we are today; will
  not scale to the new subsystems without a jungle of imports.
- **B. Multiple MCPs registered directly with Hermes** — moves
  routing/provenance into Hermes' MCP client (which we do not
  control) and breaks the current `finance.*` tool namespace.

## Consequences

### Positive

- Hermes sees one stable MCP. No config change on the Hermes side as
  we add subsystems.
- Routing, caching, retry, provenance, and error mapping remain in
  one process — one code path to audit for safety.
- Subsystems are cleanly bounded packages; each can be tested in
  isolation with `MockProvider` and fixtures.
- Ready path to promote any subsystem to its own container later.

### Negative

- One process = one blast radius: a heavy import (e.g. SEC XBRL
  parser) can slow startup for every tool. Mitigate with lazy imports.
- Gateway becomes the central choke point; must stay small and boring.

## Rejected Alternatives

- Multiple MCPs facing Hermes (Option B).
- Continuing as a flat monolith (Option A).
- Any design that exposes provider-specific tool names to Hermes
  (`finance.polygon.get_quote`) — leaks the abstraction.

## Implementation Notes

- Phase 3 will reorganize `finance_mcp/providers/` into subfolders and
  add `router.py`, `provenance.py`, `quant/`, `valuation/`,
  `research/`. `server.py` shrinks — tools call the router.
- Existing `finance.*` tool names stay stable. Any renames documented
  as aliases (following the pattern established in Phase 2).
- Startup imports must stay light; heavy subsystems (SEC XBRL,
  optional pandas ops) import lazily on first use.

## References

- ADR-0007 (overall architecture), ADR-0012 (router), ADR-0010
  (normalization), ADR-0011 (provenance).
- <https://hermes-agent.nousresearch.com/docs/reference/mcp-config-reference>
