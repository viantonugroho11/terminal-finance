# ADR-0016: Research evaluator loop with bounded iterations

## Status

Proposed — Phase 3.

## Context

Multi-agent research (ADR-0015) produces a thesis draft. Without a
gate before it reaches the user, subtle failures slip through: an
uncited number, a contradictory bull-vs-base case, a valuation that
skips a required assumption, a hallucinated news headline. We need an
evaluator that scores drafts on a fixed rubric and either accepts,
sends back for one revision, or fails the run.

Naive "improve until perfect" loops burn tokens without converging.
Bound the loop.

## Decision

We will add an **Evaluator subagent** invoked by the deep-research
orchestrator after the lead-analyst produces a thesis draft:

```
Analysts (parallel)
     ↓
Lead-analyst (synthesizes draft)
     ↓
Evaluator (scores against rubric)
     ↓ if pass → deliver
     ↓ if fail (with actionable feedback) → Lead-analyst revises
     ↓ (max 2 revisions → hard stop)
Final report + quality metadata
```

**Rubric (each dimension scored 0/1/2, must-pass ≥ threshold):**

| # | Dimension | Threshold | How it's checked |
|---|---|---|---|
| 1 | Evidence coverage | 2 | Every `[FACT]` and `[CALCULATION]` claim has ≥1 provenance id |
| 2 | Source quality | ≥1 | Load-bearing numbers (revenue, EPS, guidance) come from `PRIMARY_REGULATORY` or `STRUCTURED_DATASET` (ADR-0011) |
| 3 | Calculation correctness | 2 | Every `[CALCULATION]` claim ties to a Metric with formula + inputs (ADR-0013) |
| 4 | Citation coverage | ≥1 | News claims cite `link` + `publisher` |
| 5 | Logical consistency | 2 | No two `[ANALYSIS]` sections contradict on the same claim without an explicit contradiction call-out |
| 6 | Risk coverage | ≥1 | Report has ≥3 named risks tied to specific metrics or news items |
| 7 | Valuation quality | ≥1 (skip if no valuation section) | DCF lists all required assumptions; scenarios present (bull/base/bear) |
| 8 | Hallucination risk | 2 | No numeric claim without a matching tool result in the run transcript |

**Loop bounds:**

- **Maximum 2 revisions** (3 total drafts). Rationale: empirically,
  the first revision fixes structural gaps, the second fixes narrower
  issues; further revisions rarely improve scores and add noise
  proportional to token budget.
- Each revision receives the evaluator's structured feedback (which
  dimensions failed, with pointers to specific sections/claims).
- If the third draft still fails any threshold, the report ships with
  a **`RESEARCH QUALITY: LOW`** header naming the failed dimensions,
  and the LLM is instructed to shorten the report to only what it
  could evidence. We never quietly ship a low-quality report.

**Evaluator output shape:**

```
EVALUATION
  overall: pass | revise | fail
  scores: { evidence_coverage: 2, source_quality: 1, ... }
  failures: [
    { dimension, section_ref, claim, reason, suggested_action }
  ]
  quality_label: HIGH | MEDIUM | LOW
```

The `quality_label` is surfaced verbatim in the final report header
(ADR-0019) so the user always sees it.

## Alternatives Considered

- **No evaluator** — Phase 2 today. Ships whatever the LLM produces;
  no rubric enforcement. Rejected for research-grade output.
- **LLM-as-judge with free-form prompt** — inconsistent scores across
  runs. Rejected; use structured rubric.
- **Unbounded revision loop** — burns budget without convergence.
  Rejected; cap at 2 revisions.
- **Deterministic-only evaluation (no LLM)** — some dimensions
  (logical consistency, risk coverage) need reading comprehension.
  Rejected; hybrid: deterministic checks for coverage/citation, LLM
  for consistency/completeness.

## Consequences

### Positive

- Consistent minimum quality bar for every research report.
- User always knows the label (HIGH / MEDIUM / LOW) — no hidden
  compromise.
- Structured feedback makes revisions targeted; the lead does not
  rewrite the whole draft to fix one section.

### Negative

- +1 LLM call per draft (evaluator) + up to +2 more (revisions).
  Bounded token cost.
- Evaluator itself can be wrong. Mitigated by making its output
  reviewable in the research log and by keeping the rubric small and
  explicit.
- LOW-quality reports still ship (with the label). Some users may
  prefer a hard fail; we prefer transparency + user judgment.

## Rejected Alternatives

- No evaluator.
- Unbounded revision loop.
- Free-form LLM judge (no rubric).
- Pure deterministic evaluator.

## Implementation Notes

- `finance-skills/analysts/evaluator/SKILL.md` (or bundle inside
  `deep-research`) holds the rubric text.
- Deterministic checks (evidence-id coverage, citation presence,
  Metric ↔ formula link) are computed in
  `finance_mcp/research/evaluator_checks.py` and passed to the
  evaluator as pre-computed inputs — LLM never redoes them.
- The transcript of tool calls made during the run is the ground
  truth for dimension 8; kept in the orchestrator's working context.
- The quality label is a required field in the final report; ADR-0019
  reserves the header slot for it.

## References

- ADR-0011 (source hierarchy), ADR-0013 (metric ↔ formula ↔ inputs),
  ADR-0014 (analyst output contract), ADR-0015 (orchestration),
  ADR-0019 (report format).
