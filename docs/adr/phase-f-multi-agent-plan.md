# Phase F — Multi-agent research plan (ADR-0014 / 0015 / 0016)

Status: **planning only**. No code yet.

Multi-agent work depends on Hermes' subagent runtime, cron, and
inter-agent messaging. That runtime is external to this repo, so Phase
F is delivered as an implementation plan + acceptance criteria rather
than shipped code. When the Hermes-side prerequisites are stable, walk
this doc top-to-bottom.

## ADR-0014 — Advanced financial analyst skill decomposition

**Goal:** replace the monolithic `stock-analysis` skill with a
composed set of specialized analyst skills that a coordinator can
fan out over.

**Skill split (all under `finance-skills/`):**

| Skill                    | Role                                    | Tools it owns                                              |
|--------------------------|-----------------------------------------|------------------------------------------------------------|
| `fundamental-analysis`   | ratios, statements, quality, growth     | `get_fundamentals`, `get_financial_statements`, `get_sec_facts` |
| `technical-analysis`     | trend, momentum, volatility, drawdown   | `get_technical`, `get_historical_prices`                   |
| `valuation-analysis`     | DCF, sensitivity, reverse DCF           | `valuation_dcf`, `valuation_sensitivity`                   |
| `risk-analysis`          | portfolio risk + single-name risk       | `portfolio_risk`, `get_technical`, `get_fundamentals`      |
| `catalyst-analysis`      | news, disclosures, corp actions, IPOs   | `search_news`, `get_disclosures`, `get_corporate_actions`, `get_sec_filings` |
| `peer-analysis`          | sector peers + comps table              | `get_sector_info`, `search_stocks`, `get_fundamentals`     |
| `macro-context`          | rates, inflation, FX, banking SPI       | `get_macro`                                                |

**Coordinator skill:** `equity-research` (new). Fans out to the seven
sub-skills in parallel (Hermes subagent runtime), collates their
outputs, renders using the ADR-0019 report format.

**Migration:** existing `stock-analysis` remains but delegates to the
coordinator when Hermes subagents are available; otherwise falls back
to its current single-context procedure. Zero-break.

**Acceptance:**
- Each sub-skill emits a scoped section matching its area, tagged
  `[FACT]`/`[ANALYSIS]`/`[RISK]`.
- Coordinator preserves every citation from every sub-skill.
- Same wall-clock latency ceiling as today's `stock-analysis`
  (parallelism must be a net win, not a wash).

## ADR-0015 — Multi-agent research via Hermes subagents

**Goal:** for open-ended research ("do a deep dive on BBCA", "compare
the four Indonesian state banks"), spawn Hermes subagents that each
own one research thread and report back to a synthesizer.

**Runtime requirements from Hermes (external prerequisites):**

- Subagent spawn API with per-subagent tool whitelist.
- Message-passing envelope (parent ↔ child) with structured payloads.
- Timeout + cost budget per subagent.
- Persistent scratchpad shared across agents in a research session.

**Fan-out topology per equity deep-dive:**

```
             equity-research (coordinator)
                 │
    ┌────────────┼─────────────┬────────────┬────────────┐
    │            │             │            │            │
fundamental  technical    valuation    catalyst      peer
    │            │             │            │            │
    │            │             │            │            │
    └────────────┴──────┬──────┴────────────┴────────────┘
                        │
                  macro-context
                        │
                  synthesizer
                        │
                    evaluator  (ADR-0016)
                        │
                   final report
```

**Session state:** shared JSON scratchpad in `/opt/data/hermes/sessions/`
storing tool outputs indexed by `(symbol, capability, tool_call_id)`
so sub-skills can reuse each other's fetches without re-hitting the
provider.

**Cost controls:**
- Each subagent capped at N tool calls (config default: 12).
- Coordinator times out at 90s wall-clock and returns whatever it has
  with a `[partial]` tag on missing sections.

## ADR-0016 — Research evaluator loop with bounded iterations

**Goal:** after the synthesizer produces a draft, an evaluator agent
grades it against a rubric and either accepts or requests a bounded
number of retries.

**Rubric (weights sum to 100):**

| Criterion                                    | Weight |
|----------------------------------------------|--------|
| Every numeric claim cited to a tool result   | 25     |
| Bull case and bear case both grounded        | 15     |
| Sensitivity block reflects real ranges       | 10     |
| Risks tied to specific metrics or events     | 15     |
| No hallucinated tickers / dates / figures    | 20     |
| Report follows ADR-0019 template exactly     | 10     |
| Confidence rating matches the evidence tier  |  5     |

**Loop:**

1. Synthesizer emits draft.
2. Evaluator scores against rubric.
3. If score ≥ 80: publish.
4. If 60 ≤ score < 80: return specific rubric misses to synthesizer
   with cite of the missing tool output. Max 2 retries.
5. If score < 60 after retries: publish with a `[Low-Confidence]`
   banner and the evaluator's dissent inline.

**Anti-loop guards:**
- Rubric is deterministic (regex + citation graph check + numeric
  cross-reference). Not LLM-adjudicated.
- Evaluator gets read-only tool access — cannot invoke providers to
  "verify" (which would blow the cost budget).
- Retries capped at 2 hard.

## Implementation order once Hermes prerequisites land

1. Build `fundamental-analysis`, `technical-analysis`, `catalyst-analysis`
   as single-context skills first (no subagent runtime needed) —
   validates the decomposition.
2. Build `equity-research` coordinator that runs the sub-skills
   sequentially in one context — proves the composition without
   requiring subagents.
3. Enable subagent parallelism inside the coordinator once Hermes
   ships the runtime API.
4. Add the evaluator loop.

Steps 1–2 are shippable today without any Hermes-side change; they
are next on the roadmap after the current Fase E deliverables land.
Steps 3–4 wait for Hermes.

## Status

- Planning committed 2026-08-13.
- ADR-0014/0015/0016 remain **Proposed** in the index until steps 1–2
  ship code.
- Update this doc as prerequisites move.
