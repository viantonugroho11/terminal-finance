# Architecture Decision Records

One file per decision. Number monotonically. Never rewrite an accepted ADR — supersede it with a new one and link both.

Status vocabulary: `Proposed`, `Accepted`, `Superseded by ADR-NNNN`, `Deprecated`.

Template — copy `0000-template.md`.

Format follows MADR-lite with the sections mandated by the Phase 3 brief:
**Status · Context · Decision · Alternatives Considered · Consequences (Positive / Negative) · Rejected Alternatives · Implementation Notes · References**.

## Index

### Phase 1–2 (Accepted, in production)

| # | Title | Status |
|---|---|---|
| [0001](0001-http-mcp-transport-over-stdio.md) | HTTP MCP transport over stdio | Accepted |
| [0002](0002-provider-protocol-abstraction.md) | Provider Protocol abstraction | Accepted |
| [0003](0003-in-process-ttl-cache-with-single-flight.md) | In-process TTL cache with single-flight | Accepted |
| [0004](0004-provenance-wrapper-on-every-tool-reply.md) | Provenance wrapper on every tool reply | Accepted |
| [0005](0005-structured-finance-errors-with-stable-codes.md) | Structured FinanceError with stable codes | Accepted |
| [0006](0006-fastmcp-shim-for-offline-python39-tests.md) | FastMCP shim for offline / Python 3.9 tests | Accepted |

### Phase 3 (Proposed — architectural gate before implementation)

| # | Title | Status |
|---|---|---|
| [0007](0007-finance-hermes-architecture.md) | Finance Hermes overall architecture (target stack) | Proposed |
| [0008](0008-multi-provider-financial-data.md) | Multi-provider financial data with capability tags | Proposed |
| [0009](0009-finance-mcp-architecture.md) | Finance MCP shape — gateway + specialized backends | Proposed |
| [0010](0010-financial-data-normalization.md) | Canonical financial data models + schema versioning | Proposed |
| [0011](0011-financial-data-provenance.md) | Data provenance, source hierarchy, conflict resolution | Proposed |
| [0012](0012-intelligent-provider-routing.md) | Capability-based provider router | Proposed |
| [0013](0013-quantitative-analysis-engine.md) | Quantitative analysis engine (deterministic math) | Proposed |
| [0014](0014-advanced-financial-analyst-skills.md) | Advanced financial analyst skill decomposition | Proposed |
| [0015](0015-multi-agent-financial-research.md) | Multi-agent financial research via Hermes subagents | Proposed |
| [0016](0016-research-evaluation-and-quality.md) | Research evaluator loop with bounded iterations | Proposed |
| [0017](0017-valuation-and-dcf-engine.md) | DCF and valuation engine (deterministic) | Proposed |
| [0018](0018-sec-and-primary-source-integration.md) | SEC EDGAR and primary-source integration | Proposed |
| [0019](0019-finance-research-output.md) | Deep-research report format and rendering | Proposed |

### Indonesia extension (Phase A/B)

| # | Title | Status |
|---|---|---|
| [0020](0020-indonesian-market-data-providers.md) | Indonesian market data providers (IDX/BEI, BI, BPS, OJK) | Accepted (Phase B: IDX landed) |
| [0021](0021-market-detection-and-symbol-routing.md) | Market detection and symbol-based routing | Accepted |

## Supporting docs

- [Phase 3 architecture decision matrix](phase-3-decision-matrix.md) — quick-glance table of decisions, alternatives, and rationale.
- [Phase 3 reference analysis](phase-3-reference-analysis.md) — external projects reviewed (Alpha Vantage MCP, Financial Datasets MCP, MCP FinanceX, FinRobot, FinSphere): what we learn, what we do NOT copy.
- [Phase 3 implementation sequence](phase-3-implementation-sequence.md) — recommended build order once ADRs are Accepted.
- [Phase A — Indonesia findings](phase-a-indonesia-findings.md) — architecture map, provider decision matrix, license notes.
