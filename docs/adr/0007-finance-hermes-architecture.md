# ADR-0007: Finance Hermes overall architecture (Phase 3 target)

## Status

Accepted (Phase E landed 2026-08-13). Target architecture is now the
in-production shape: Hermes (unmodified) + finance-mcp sidecar with
router-selected providers (yahoo, idx, bi, bps, ojk, sec, mock), plus
finance-skills orchestrating tool calls. Compose stack ships in
`docker/`. README §Architecture reflects the same picture. Extends
ADR-0001 (transport), ADR-0002 (Protocols).

## Context

Phases 1–2 shipped a working vertical slice: Hermes → one Finance Skill
→ one Finance MCP (`finance-mcp`) → one provider (`yahoo`). The Phase 3
brief asks for multi-provider data, capability-based routing, a
quantitative engine, multi-agent research with a lead + specialist
analysts, an evaluator loop, DCF valuation, SEC primary-source
integration, and a structured research report.

Before any of that ships, we need to lock the shape of the layered
system so later ADRs (0008–0019) can slot into named boxes.

Existing anchors in the repo:

- Hermes owns: agent runtime, memory, skill loader, MCP client, cron,
  provider (LLM) routing, subagents, terminal backends.
  (Source: <https://hermes-agent.nousresearch.com/docs>.)
- Finance layer owns: skills (`finance-skills/`), MCP sidecar
  (`finance-mcp/`), portfolio SQLite, providers, normalized models,
  deterministic calc/technical packages, SOUL persona and safety.

## Decision

We will keep Hermes untouched and layer the finance domain in the
following stack, each layer depending only on the ones beneath it:

```
                    HERMES AGENT (unchanged)
                              │
                              ▼
                       FINANCE SKILLS
                              │
                              ▼
                    RESEARCH ORCHESTRATOR
                    (skill that fans out to
                    Hermes subagents)
                              │
                              ▼
                     FINANCE MCP LAYER
                     (see ADR-0009: gateway
                      + specialized MCPs)
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
         Market Data     Fundamentals      Research
          providers        providers        providers
                              │
                              ▼
                    DATA NORMALIZATION
                    (canonical models,
                     ADR-0010)
                              │
                              ▼
                     DATA QUALITY &
                       PROVENANCE
                    (source hierarchy,
                     ADR-0011)
                              │
                              ▼
                        QUANT ENGINE
                    (deterministic math,
                     ADR-0013)
                              │
                              ▼
                    ANALYST SUBAGENTS
                    (ADR-0014, ADR-0015)
                              │
                              ▼
                       EVALUATOR LOOP
                       (ADR-0016)
                              │
                              ▼
                   INVESTMENT THESIS
                       (ADR-0019)
```

## Alternatives Considered

- **Fold everything into one Finance MCP** — simpler for now, but by
  Phase 8 the router, quant engine, and SEC parser all live inside a
  single Python process with wildly different dependency footprints.
  Rejected via ADR-0009.
- **Replace Hermes with a custom orchestrator** — rejected: the whole
  project premise is "do not rebuild Hermes"; we lose memory, cron,
  subagents, MCP client, provider routing for zero gain.
- **Skip the Research Orchestrator; put fan-out in each Skill** — each
  skill would grow its own orchestration; drift is guaranteed.
  Centralize in one orchestrator (ADR-0015).

## Consequences

### Positive

- Each new capability lands in a named box with defined boundaries.
- Providers, normalization, quant, analysts, evaluator, and report can
  each be replaced without touching neighbors.
- Hermes upgrades stay drop-in — we never modify its runtime.

### Negative

- More surface area to keep coherent — 13 ADRs to enforce.
- The Research Orchestrator becomes a load-bearing skill; regressions
  there cascade into every deep-research answer.
- Layered indirection has a latency cost (measured in ms, dwarfed by
  provider RTT). Non-issue.

## Rejected Alternatives

- Hermes fork (owning agent runtime ourselves).
- Single-MCP monolith with in-process everything.
- LLM-only research pipeline with no deterministic quant engine.

## Implementation Notes

- No code change from this ADR. Every subsequent Phase 3 ADR points
  its "where does this live" back to a box in the stack above.
- The Research Orchestrator will be a new skill file
  (`finance-skills/deep-research/SKILL.md`) — created only in Phase 3.

## References

- ADR-0001, ADR-0002 (existing transport + provider abstraction).
- ADR-0008 through ADR-0019 (the concrete decisions filling this stack).
- <https://hermes-agent.nousresearch.com/docs/user-guide/features/skills>
- <https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp>
