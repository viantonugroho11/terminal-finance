# ADR-0014: Advanced financial analyst skill decomposition

## Status

Accepted for single-context composition (Phase F Steps 1–2 landed
2026-08-13). Ships six specialist skills — `fundamental-analysis`,
`technical-analysis`, `catalyst-analysis`, `peer-analysis`,
`macro-context`, `valuation-analysis` — plus the `equity-research`
coordinator that runs them inline in one Hermes context. Fan-out via
Hermes subagents (Phase F Step 3, ADR-0015) waits on external Hermes
runtime; the coordinator's Procedure section documents the switch
point when it lands. See `docs/adr/phase-f-multi-agent-plan.md`.

## Context

Existing skills (`stock-analysis`, `crypto-analysis`,
`portfolio-analysis`, `risk-analysis`, `market-overview`) each follow
one pattern: fetch data → format sections → let the LLM synthesize.
That is enough for a quote-and-comment answer. It is not enough for a
research-grade thesis with quantified risk, valuation, catalysts, and
a contradiction check.

Phase 3 needs specialized analyst skills that can be composed by a
lead skill (ADR-0015) into a coherent report (ADR-0019).

## Decision

We will introduce a specialist-skill layout under
`finance-skills/analysts/` — each skill is a Hermes skill file per
existing conventions (ADR-0007 stack), each with a narrow scope, a
required-tools list from the Finance MCP, and an output contract
consumed by the lead:

```
finance-skills/
├── analysts/
│   ├── fundamental-analyst/SKILL.md
│   ├── valuation-analyst/SKILL.md
│   ├── technical-analyst/SKILL.md
│   ├── risk-analyst/SKILL.md
│   ├── news-catalyst-analyst/SKILL.md
│   ├── competitive-analyst/SKILL.md
│   └── lead-analyst/SKILL.md
└── deep-research/SKILL.md      # orchestrator entrypoint (ADR-0015)
```

**Analyst contract (shared):**

Every analyst SKILL.md declares:

- `role` — one sentence, unique per analyst.
- `inputs` — list of MCP tools the analyst is allowed to call.
- `output_format` — structured markdown with `[FACT] / [CALCULATION] /
  [ANALYSIS] / [RISK]` tags (Phase 2 convention) plus a required
  `EVIDENCE` block that lists provenance ids for every claim.
- `refusal_rules` — when to return "not enough evidence" instead of
  synthesizing. Example: valuation-analyst refuses when
  `financial_statements` returned `{error}`; it does not guess.

**Responsibilities (short form; each SKILL.md is the source of truth):**

| Analyst | Owns | Tools |
|---|---|---|
| Fundamental | Revenue trend, margin quality, growth, capital efficiency | `get_financial_statements`, `get_fundamentals`, `quant.ratios` |
| Valuation | DCF (base/bull/bear), relative-multiple sanity check, upside/downside | `get_valuation` (ADR-0017), `quant.ratios`, `get_fundamentals` |
| Technical | Trend, momentum, volatility, support/resistance | `get_historical_prices`, `get_technical` |
| Risk | Concentration, leverage, drawdown, macro sensitivity | `quant.risk`, `get_historical_prices`, `portfolio_risk` (if portfolio context) |
| News/Catalyst | Recent narrative, scheduled events (earnings/guidance), regulatory | `search_news`, `get_filings` (ADR-0018) |
| Competitive | Peer set, comparative multiples, moat framing | `get_company_profile`, `get_fundamentals` across peers |
| Lead | Task decomposition, synthesis, contradiction check, thesis | subagents (Hermes), all above |

**Explicit non-goals:**

- Skills do NOT call provider adapters directly — always via MCP tools.
- Skills do NOT do arithmetic — always via `finance.get_technical`,
  `finance.get_valuation`, `quant.*` metrics. LLM interprets numbers,
  never computes them.
- Skills do NOT recommend `BUY/SELL/HOLD` — thesis presents bull /
  base / bear with confidence.

## Alternatives Considered

- **One giant `deep-research` skill with all logic inline** — reads
  like a 2000-line SKILL.md; impossible to iterate on one analyst
  without risking the others. Rejected.
- **Function-style tools (no skills, just MCP calls)** — loses the
  Hermes skill-loader benefits (auto-context, blueprint scheduling,
  Curator staleness tracking). Rejected.
- **Analyst = Python code, not a skill** — moves LLM prompting into
  code (worse iteration loop) and duplicates what Hermes skills
  already provide. Rejected.

## Consequences

### Positive

- Each analyst is small, focused, and independently testable
  (prompt-eval fixtures per analyst).
- Adding a new analyst (e.g. ESG, macro) = one folder + one entry in
  `lead-analyst`'s subagent registry.
- Failure isolation: if the technical analyst returns "n/a," the
  fundamental analyst still ships evidence into the thesis.

### Negative

- More skill files to maintain; SKILL.md drift risk. Mitigated by a
  shared "analyst contract" doc referenced by each SKILL.md.
- The lead-analyst prompt is where thesis quality lives — worth
  disproportionate iteration effort.

## Rejected Alternatives

- Monolithic deep-research skill.
- Analyst-as-Python-module (bypasses Hermes skill system).
- LLM-computed metrics inside analyst skills.

## Implementation Notes

- Add `finance-skills/analysts/README.md` documenting the shared
  Analyst Contract (once) so each SKILL.md can reference it.
- `lead-analyst` SKILL.md is short — its job is to spawn subagents
  (ADR-0015), pass evidence, and synthesize. It does not itself
  gather data.
- The `EVIDENCE` block format is standardized: `- <claim> — [<provenance_id>]`.
  Report renderer (ADR-0019) links these to full provenance.

## References

- ADR-0007 (architecture stack), ADR-0011 (provenance ids),
  ADR-0013 (quant engine), ADR-0015 (multi-agent orchestration),
  ADR-0016 (evaluator), ADR-0019 (report format).
- Existing SKILL.md files under `finance-skills/`.
