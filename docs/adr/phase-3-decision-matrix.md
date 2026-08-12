# Phase 3 Architecture Decision Matrix

Quick-glance summary of every Phase 3 architectural decision. Full context in each ADR.

| Area | Chosen Approach | Alternatives Rejected | Reason | ADR |
|---|---|---|---|---|
| Agent runtime | Hermes (unchanged) | Custom runtime, LangGraph, CrewAI | Reuse existing memory / subagents / cron / MCP client; the whole project premise | [0007](0007-finance-hermes-architecture.md) |
| Data providers | Multi-provider with capability + tier tags | Yahoo-only; wrap external MCPs | Reliability, coverage, quality tiering | [0008](0008-multi-provider-financial-data.md) |
| MCP topology | One Finance MCP gateway → internal specialized subsystems | Monolith; N MCPs facing Hermes | Consistent provenance/errors; Hermes sees one stable surface | [0009](0009-finance-mcp-architecture.md) |
| Data model | Canonical dataclasses + `SCHEMA_VERSION` + explicit units/period | Provider dicts; per-provider models; Pydantic runtime validation | Decouple skills from vendors; cache-safe evolution | [0010](0010-financial-data-normalization.md) |
| Provenance | 7-tier source hierarchy + `DataConflict` on same-tier disagreement | First-wins; LLM adjudication; weighted average | Every load-bearing number traces to a primary source | [0011](0011-financial-data-provenance.md) |
| Provider routing | Capability-based router with declared fallback chains in config | Static per-tool provider; LLM-chosen; round-robin | Deterministic, testable, tunable per deployment | [0012](0012-intelligent-provider-routing.md) |
| Calculations | Deterministic `quant/` package returning `Metric{formula,inputs,provenance}` | LLM math; naked floats; vendored TA-Lib | Accuracy + audit trail; LLM never source of arithmetic truth | [0013](0013-quantitative-analysis-engine.md) |
| Skill structure | Specialist analyst skills + lead orchestrator | One giant deep-research skill; analyst-as-Python | Independent iteration, failure isolation | [0014](0014-advanced-financial-analyst-skills.md) |
| Research orchestration | Hermes subagents with task envelope + `RESULT` contract | Sequential pipeline; custom framework | Parallelism, per-analyst context, no runtime rebuild | [0015](0015-multi-agent-financial-research.md) |
| Quality gate | Bounded evaluator loop (rubric + max 2 revisions + `QUALITY:` header) | No gate; unbounded loop; free-form judge | Consistent minimum quality; token budget | [0016](0016-research-evaluation-and-quality.md) |
| Valuation | Deterministic DCF with explicit `Assumption` objects + bull/base/bear + sensitivity | LLM-DCF; hidden defaults; comps-only; Monte-Carlo in Phase 3 | No fabricated assumptions; heuristic flags force LOW confidence | [0017](0017-valuation-and-dcf-engine.md) |
| Primary sources | Direct SEC EDGAR adapter (`PRIMARY_REGULATORY` tier) + narrow XBRL | Aggregators only; Financial Datasets sole primary; wrap external SEC-MCP | Every DCF input traceable to an accession | [0018](0018-sec-and-primary-source-integration.md) |
| Research output | One canonical report format with `RESEARCH QUALITY` + `CONFIDENCE` headers, no `BUY/SELL/HOLD` | Free-form per skill; JSON-only; rating labels; auto-publish | Testable, diffable, safe by construction | [0019](0019-finance-research-output.md) |

## Cross-cutting constraints

- **Do not rebuild Hermes.** Every ADR is checked against this rule.
- **No fabricated data.** `None` beats fake; conflicts surface, never hide; DCF assumptions are explicit and flagged.
- **Deterministic math.** LLM interprets, never computes.
- **Provenance everywhere.** Every user-facing number has a provider, a tier, a timestamp, and (for derived) its inputs.
