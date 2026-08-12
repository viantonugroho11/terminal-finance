# ADR-0015: Multi-agent financial research via Hermes subagents

## Status

Proposed — Phase 3.

## Context

Deep research needs specialist analysts (ADR-0014) that work in
parallel, each with its own context window, and a lead that
synthesizes. Hermes already provides a subagent runtime — its
Persistent Goals + subagent primitives are documented in its features
docs. The project's binding constraint is **"do not rebuild Hermes."**

We must not:

- introduce a bespoke agent framework;
- reinvent task dispatch;
- copy FinRobot / FinSphere codebases (learn from concepts only).

## Decision

We will implement multi-agent research as a **Hermes-native pattern**:

- The `deep-research` skill (entrypoint) is the orchestrator. When
  invoked, it plans the research (list of analysts to run, symbols to
  cover, budgets), then spawns each analyst as a **Hermes subagent**
  invoking the corresponding analyst skill (ADR-0014).
- Every subagent receives a **task envelope** with a fixed shape,
  passed via prompt:

  ```
  TASK: <analyst role>
  SYMBOL: <SYM>
  CONTEXT: <shared research plan snippet>
  TOOL WHITELIST: <finance.* tool names>
  MAX TOKENS: <budget>
  DEADLINE: <ISO time or "no deadline">
  OUTPUT CONTRACT: <link to analyst SKILL.md output section>
  EVIDENCE POLICY: cite provenance ids for every claim.
  REFUSAL POLICY: return "insufficient evidence" instead of guessing.
  ```

- Every subagent returns a **structured result** in a fenced block:

  ```
  RESULT
  ANALYST: fundamental
  STATUS: ok | partial | insufficient_evidence | error
  SECTIONS: [...]        # markdown per analyst's output_format
  EVIDENCE: [...]        # list[{claim, provenance_ids}]
  METRICS: [...]         # list[Metric] surfaced for the lead
  ERRORS: [...]          # list[{code, message}] from any tool failure
  ```

- The lead runs a **contradiction check** across all subagent results
  before writing the thesis. When two subagents disagree on a claim
  covered by primary sources, the higher tier wins (ADR-0011); when
  same-tier, the contradiction is surfaced in the thesis, not hidden.

- **Retry policy:** a subagent that returns `error` on transient
  Finance MCP errors (`TIMEOUT`, `RATE_LIMITED`, `PROVIDER_UNAVAILABLE`)
  gets one re-dispatch. `insufficient_evidence` is not an error — the
  lead notes the gap in the report.

- **Timeout / budget:** the orchestrator declares a total budget
  (default ~60s / ~80k tokens) and per-analyst budgets summing to it.
  Subagents that miss the deadline are reported as `status: partial`
  with whatever they finished; the lead does not wait past the
  budget.

- **Sequence:** analysts run **in parallel** (they are independent);
  the lead runs only after all subagents return (or the budget
  elapses). Evaluator (ADR-0016) runs after the lead.

## Alternatives Considered

- **Sequential pipeline through one skill** — cheaper but slow (~5×
  wall clock) and single-context (topic drift). Rejected.
- **Custom multi-agent framework in Python** — violates the "do not
  rebuild Hermes" rule; Hermes already provides subagents. Rejected.
- **LangGraph / CrewAI on top** — extra runtime and framework
  gravity for a problem Hermes already solves. Rejected.
- **Free-form LLM planning without a task envelope** — envelope is
  the contract; without it subagents ignore tool whitelists and
  evidence policy. Rejected.

## Consequences

### Positive

- Parallel analyst work; wall-clock dominated by the slowest analyst,
  not the sum.
- Each analyst has its own context window — no topic bleed from
  fundamentals into technicals.
- The task envelope + result contract makes any bad subagent output
  detectable and rejectable at the lead / evaluator stage.
- Reuses Hermes primitives; no new framework to own.

### Negative

- Total token spend goes up (parallel analysts + lead + evaluator).
  Budget per analyst mitigates.
- Debugging multi-agent runs is harder than single-thread traces.
  Structured `RESULT` blocks + evidence ids help; we may add a
  research-log tool in a later ADR.
- Depends on Hermes subagent stability — if the subagent runtime
  changes, we adapt the envelope shape.

## Rejected Alternatives

- Custom agent framework.
- Sequential single-skill pipeline.
- LangGraph / CrewAI overlays.
- Free-form (no task envelope) delegation.

## Implementation Notes

- `finance-skills/deep-research/SKILL.md` is the entrypoint. It
  documents the envelope + result contracts as ready-to-paste blocks.
- `finance-skills/analysts/README.md` (Analyst Contract) says every
  analyst SKILL.md MUST accept the envelope and MUST emit a `RESULT`
  block.
- The orchestrator does not itself hit the Finance MCP — data
  fetching lives inside the subagents.
- Reference reading (concepts, not code): FinRobot, FinSphere. Do
  NOT copy their runtimes; borrow the analyst decomposition.

## References

- ADR-0007, ADR-0014 (analyst skills), ADR-0011 (provenance),
  ADR-0016 (evaluator), ADR-0019 (report).
- <https://hermes-agent.nousresearch.com/docs/user-guide/features/goals>
  (subagent-adjacent primitives)
- FinRobot / FinSphere — for the decomposition idea only.
