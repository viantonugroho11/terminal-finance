# ADR-0013: Quantitative analysis engine (deterministic math)

## Status

Proposed — Phase 3. Extends `finance_mcp/calc.py` and
`finance_mcp/technical.py` (Phase 2).

## Context

Phase 2 introduced `calc.py` (percentage_change, returns, averages,
CAGR, market_cap, enterprise_value) and `technical.py` (SMA, EMA, RSI,
MACD, volatility, drawdown). Every result is deterministic; the LLM
never does the arithmetic.

Phase 3 adds risk metrics (Sharpe, Sortino, VaR, CVaR, beta, correl),
more technicals (ATR), and fundamental ratios (P/E, P/S, P/B,
EV/EBITDA, FCF yield, PEG). DCF gets its own home (ADR-0017).
Analyst subagents (ADR-0014) will call the quant engine for every
number that shows up in a thesis.

The engine must:

- Return unit-safe values (ADR-0010).
- Emit provenance with `source_class: DERIVED` and `inputs: [...]`
  linking back to raw provenance ids (ADR-0011).
- Be pure (no I/O), so it can be tested with fixtures and reused by
  the router, valuation subsystem, and analyst subagents.
- Refuse to compute when inputs are missing — return `None`, never a
  fabricated placeholder.

## Decision

We will create `finance_mcp/quant/` as a package with sub-modules:

```
finance_mcp/quant/
├── __init__.py       # re-exports; SCHEMA_VERSION
├── returns.py        # simple, log, cumulative, CAGR, annualized
├── risk.py           # volatility, downside_vol, Sharpe, Sortino,
│                     #   max_drawdown, beta, correlation, VaR, CVaR
├── technical.py      # (existing) SMA, EMA, RSI, MACD, ATR, Bollinger
├── ratios.py         # P/E, P/S, P/B, EV/EBITDA, PEG, FCF yield,
│                     #   ROE, ROA, ROIC, debt/equity, current ratio
├── portfolio.py      # weighted returns, contribution, HHI, tracking error
└── metric.py         # Metric{name, value, unit, formula, inputs, provenance}
```

Every function follows the same signature contract:

```python
def <metric>(*inputs, **params) -> Metric | None
```

- Returns a `Metric` on success, `None` on missing inputs — never
  raises for missing data.
- `Metric.provenance.source_class = "DERIVED"`; `Metric.inputs` lists
  the provenance ids of every raw value consumed.
- `Metric.formula` is a short human-readable string
  (e.g. `"P/E = price / eps"`), for the report's audit trail.

The engine has no MCP tools of its own by default; it is called from
inside `get_technical`, `get_fundamentals`, `get_valuation`, and the
analyst subagents. If the user later wants raw quant tools exposed
(e.g. `finance.compute_sharpe`), that is one line per exposure.

**Explicit non-goals:**

- No time-series storage. Callers pass canonical `list[Candle]` /
  `Financials` objects. The engine does not fetch data.
- No optimization / backtesting framework in Phase 3. Enough surface
  to write a rigorous single-name thesis.
- No opinion. Metrics are neutral; interpretation is the analyst's
  job.

## Alternatives Considered

- **Let the LLM compute** — banned by SOUL and by the "deterministic
  calculations" mandate. Rejected.
- **Depend on TA-Lib / QuantLib** — heavy binary deps; overkill for
  the metric set above. Revisit if we need exotic instruments.
- **One flat module** — will not scale past ~20 functions cleanly.
- **Return raw floats** — loses provenance and formula; makes audit
  impossible. Rejected.

## Consequences

### Positive

- Every number in a research report has a formula + inputs +
  provenance. Full audit trail from thesis back to raw filing.
- Skills and analyst subagents share one implementation of every
  metric — no drift between technical-analyst and risk-analyst.
- Missing-input semantics are honest: `None` propagates, never a fake
  zero or "N/A" string masquerading as a number.

### Negative

- Every raw provider dataclass loaded into the quant engine must
  carry provenance ids; small refactor to pass ids alongside values.
- `Metric` objects are heavier than floats — memory and JSON size
  grow. Trivial for research-scale usage.

## Rejected Alternatives

- LLM-computed math.
- Vendored TA-Lib (Phase 3 scope).
- Naked floats without provenance.

## Implementation Notes

- Move `finance_mcp/technical.py` under `finance_mcp/quant/` with a
  compat re-export at the old path for one release, then delete.
- Split `finance_mcp/calc.py` between `quant/returns.py` and
  `quant/ratios.py` similarly.
- `Metric` dataclass lives in `quant/metric.py`; models.py imports it
  for use in report structures.
- Tests: keep the existing test files, add per-module unit tests with
  hand-computed fixtures.

## References

- ADR-0010 (canonical models), ADR-0011 (provenance & DERIVED),
  ADR-0017 (DCF is its own subsystem).
- Existing files: `finance_mcp/calc.py`, `finance_mcp/technical.py`.
