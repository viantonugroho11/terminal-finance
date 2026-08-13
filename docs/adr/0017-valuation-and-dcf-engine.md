# ADR-0017: DCF and valuation engine (deterministic, scenario-based)

## Status

Accepted (Phase E landed 2026-08-13). Ships `finance_mcp/valuation.py`
with pure functions (`capm`, `wacc`, `cagr`, `project_fcf`,
`terminal_value_gordon`, `npv`, `dcf`, `sensitivity_table`,
`implied_growth`) and two MCP tools (`valuation_dcf`,
`valuation_sensitivity`) that assemble inputs from statements/
fundamentals through the router and hand them to the pure math.
Skill `valuation-analysis` orchestrates + interprets. Reverse-DCF
(`implied_growth`) is library-only for now — surface as a tool if a
skill needs it. Extends ADR-0013 (quant engine contract).

## Context

Fair-value estimation cannot be left to the LLM. The failure mode is
too easy: the model invents a discount rate, invents a terminal
growth rate, and produces a fair value that sounds authoritative and
has no audit trail. Every DCF assumption must be explicit, sourced,
and challengeable.

The Phase 3 brief §14 requires deterministic valuation with
bull / base / bear scenarios and explicit protection against the
LLM silently inventing assumptions.

## Decision

We will add `finance_mcp/valuation/` as a subsystem package with:

```
finance_mcp/valuation/
├── __init__.py            # SCHEMA_VERSION; re-exports
├── dcf.py                 # DCF engine (pure math)
├── assumptions.py         # Assumption dataclass + validation
├── scenarios.py           # bull/base/bear composition
├── comps.py               # relative multiples sanity check
└── output.py              # Valuation model (from ADR-0010)
```

**Required DCF inputs (all explicit — no defaults hidden in code):**

- `revenue_base` (with `Provenance`)
- `revenue_growth_annual[]` (list per forecast year)
- `ebit_margin[]`
- `tax_rate`
- `da_pct_of_revenue[]`
- `capex_pct_of_revenue[]`
- `working_capital_pct_of_revenue[]`
- `wacc`
- `terminal_growth`
- `forecast_years` (default 5, must be explicit in the call)
- `shares_outstanding` (with `Provenance`)
- `net_debt` (with `Provenance`)

**Assumption discipline:**

- Every input is an `Assumption(value, source, rationale, provenance)`
  where `source ∈ {DERIVED, ANALYST_INPUT, CONSENSUS, HEURISTIC}`.
- `HEURISTIC` values (e.g. WACC = 10% because no better estimate) are
  ALLOWED but flagged in the output and the report. Any DCF with ≥1
  heuristic assumption ships with `confidence: LOW`.
- If a required input is missing, the engine returns `None` — never
  a fabricated value.

**Output shape** (`Valuation` from ADR-0010):

```
Valuation {
  method: "DCF"
  as_of: ISO
  scenarios: {
    bear: { enterprise_value, equity_value, fair_value_per_share,
            upside_pct, assumptions[] }
    base: { ... }
    bull: { ... }
  }
  sensitivity: {                # tornado-style
    wacc: [(delta, fair_value), ...]
    terminal_growth: [...]
    ebit_margin: [...]
  }
  comps: { peer_symbols[], median_pe, median_ev_ebitda,
           implied_price_from_median }
  confidence: HIGH | MEDIUM | LOW
  provenance: Provenance         # source_class: DERIVED, inputs: [assumption ids]
}
```

**Scenario construction:**

- `base` uses the analyst's central estimates.
- `bull` and `bear` apply named deltas per assumption (default
  `±2pp` on growth, `±100bps` on margin, `±100bps` on WACC). Deltas
  are configurable; the actual values used ship in the output.
- Scenarios are computed deterministically, not sampled — same inputs
  → same three outputs, always.

**MCP tool exposure** (added in Phase 3 implementation, not this ADR):

- `finance.get_valuation(symbol, assumptions?)` — returns a
  `Valuation`. Called by the valuation-analyst skill (ADR-0014).

## Alternatives Considered

- **Let the LLM compute DCF** — banned by SOUL and Phase 2 rules.
  Rejected.
- **Monte-Carlo DCF** — nice to have; scope creep for Phase 3. Add
  in a later ADR when the deterministic engine is stable.
- **Default WACC / terminal growth constants** — invites the exact
  fabrication mode we want to prevent. Rejected — force explicit
  assumptions, tag `HEURISTIC` when a fallback is used.
- **Comps-only valuation (skip DCF)** — comps are a sanity check,
  not a substitute for DCF; they carry sector-level distortions.
  Include both.

## Consequences

### Positive

- Every fair-value number in a research report has an assumption
  block the user can inspect, argue with, and re-run.
- Bull/base/bear + sensitivity table replaces "the fair value is X"
  with a range, which is what real analysts do.
- Heuristic assumptions are visible; a valuation propped up by
  guesses is labeled `LOW` confidence — no hiding.

### Negative

- DCF requires structured `FinancialStatements` from a primary
  source (ADR-0018) to be meaningful. Without SEC data, DCF quality
  drops fast and confidence tags reflect that.
- The valuation-analyst SKILL.md carries a heavier responsibility
  than other analysts; it must build the assumption set before it
  can call `get_valuation`.

## Rejected Alternatives

- LLM-computed DCF.
- Hidden default assumptions.
- Monte-Carlo DCF in Phase 3.
- Comps-only valuation.

## Implementation Notes

- `finance_mcp/valuation/` is a new subsystem package (per ADR-0009).
- Inputs come from the Fundamental analyst (revenue, margins) +
  Financial Datasets / SEC (statements) + Analyst Input (WACC,
  terminal growth) + Comps (peer set).
- Sensitivity ranges are hardcoded defaults in `scenarios.py`, with
  overrides via the tool call — never silent overrides.
- Tests: fixture DCFs with known outputs; a canonical NVDA-like case
  used as regression baseline.

## References

- ADR-0010 (Valuation model), ADR-0011 (provenance for inputs),
  ADR-0013 (quant engine shares Metric conventions),
  ADR-0014 (valuation-analyst), ADR-0018 (primary sources).
- Phase 3 spec §14.
