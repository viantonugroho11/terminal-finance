# ADR-0019: Deep-research report format and rendering

## Status

Accepted (Phase E landed 2026-08-13). Template + section grammar +
citation rules live at `docs/report-format-template.md`. Renderer
implementations (terminal TUI, HTML pandoc template, Slack digest)
follow-up work — the format itself is now fixed at version 1.0.
Skills MUST emit reports matching the template; skill authors treat
it as a contract, not a suggestion.

## Context

Analyst outputs (ADR-0014), multi-agent synthesis (ADR-0015), and
evaluator scoring (ADR-0016) all converge on one artifact: the
research report the user sees. Its shape must be predictable enough
for downstream automation (weekly report skill, watchlist digest,
Confluence publish) and rigorous enough that every important claim is
traceable to a primary source.

Ad-hoc report shapes across skills will produce inconsistent quality;
one canonical format enforces the discipline the earlier ADRs set up.

## Decision

We will define the **canonical deep-research report** as follows and
require the deep-research skill (and any skill that produces a
research-grade artifact) to emit exactly this structure:

```
<SYMBOL> — DEEP RESEARCH
────────────────────────────────────────────────────────────────
RESEARCH QUALITY: HIGH | MEDIUM | LOW      (from evaluator, ADR-0016)
CONFIDENCE:       HIGH | MEDIUM | LOW      (analyst self-assessment)
AS OF:            ISO timestamp
DATA WINDOW:      e.g. FY2023–FY2025 + Q1 2026

EXECUTIVE SUMMARY
  3–5 sentences. Neutral tone. No BUY/SELL/HOLD. Includes headline
  fair-value range and 12-month outlook framing.

BUSINESS                                                    [FACT]
  What the company does. Sourced from company profile + latest 10-K.

FINANCIAL PERFORMANCE                                       [FACT]
  Revenue / margin / EPS trend, 3y minimum. Each number tagged with
  provenance id.

FUNDAMENTALS                                                [FACT + CALCULATION]
  Ratios (P/E, P/S, EV/EBITDA, ROE, ROIC, D/E, FCF yield) with
  Metric formulas + inputs. Compared vs 5y median and peer median.

VALUATION                                                   [CALCULATION]
  DCF scenarios (bear/base/bull) with assumption block.
  Comps sanity check.
  Sensitivity table (WACC × terminal growth).
  Explicit HEURISTIC flags on any assumption without a source.

TECHNICAL ANALYSIS                                          [FACT]
  Trend, momentum (RSI, MACD), 30d/90d/1y vol, max DD.
  Cited support/resistance if identified.

COMPETITIVE POSITION                                        [ANALYSIS]
  Peer set (from Competitive analyst). Moat framing tied to
  metrics, not narrative.

CATALYSTS                                                   [FACT]
  Scheduled events (earnings, guidance, product cycle). Cite dates
  and source (SEC 8-K, IR calendar, or reputable news).

RISKS                                                       [RISK]
  ≥3 named risks tied to specific metrics, news items, or filings.
  Include probability × impact where estimable, else qualitative.

BEAR CASE / BASE CASE / BULL CASE                           [ANALYSIS]
  Each: 3–5 bullets tied to the valuation scenario of the same name.
  Bull and bear MUST cite specific assumption deltas from valuation.

WHAT WOULD CHANGE MY MIND?                                  [ANALYSIS]
  Named observable signals that would move the thesis from
  base → bull or base → bear.

KEY METRICS TO MONITOR                                      [FACT]
  Named data points + suggested cadence. Feeds Phase 8 alerts.

INVESTMENT THESIS                                           [ANALYSIS]
  2–3 sentence summary. States base-case fair value range and the
  central hypothesis. Not advice.

SOURCES
  · <source_class> — <label> — <link/accession/publisher>
  · ... one line per distinct source used in the report.

EVIDENCE APPENDIX (optional, machine-readable)
  { <provenance_id>: { source, source_class, retrieved_at, ... }, ... }
```

**Rendering rules:**

- Every `[FACT]` and `[CALCULATION]` line MUST link (or annotate)
  ≥1 provenance id present in `SOURCES` / `EVIDENCE APPENDIX`.
- Report is markdown by default. Optional JSON envelope (`{header,
  sections, sources, evidence}`) is offered when the caller sets a
  `format=json` flag on the deep-research tool — for downstream
  automation.
- `RESEARCH QUALITY` and `CONFIDENCE` are two orthogonal fields:
  quality = evaluator's rubric score; confidence = analyst's own
  read of data completeness. A HIGH-quality report can still carry
  MEDIUM confidence when data was thin.
- Persistence: reports are stored under `~/.hermes/finance/research/
  <SYMBOL>/<YYYY-MM-DD>-<hash>.md` so the user can diff runs over
  time.

**Non-goals:**

- No recommendation labels (`BUY/SELL/HOLD`). Persona rule (SOUL.md).
- No price targets stated as single points — always ranges.
- No user-facing PDF/HTML rendering in Phase 3 (Markdown persists;
  downstream skills can transform later).

## Alternatives Considered

- **Free-form report per skill** — inconsistency across runs;
  evaluator cannot rubric-check reliably. Rejected.
- **JSON-only output, no markdown** — hostile to the CLI user
  experience. Offer both; markdown primary.
- **Include BUY/SELL/HOLD as a "summary rating"** — forbidden by
  SOUL. Rejected.
- **Auto-publish to Confluence / Slack** — belongs to a later
  integration ADR, not Phase 3 core.

## Consequences

### Positive

- Report shape is stable enough to write regression tests
  ("run deep-research on NVDA fixture; assert sections + evidence
  ids present").
- Downstream automation (weekly digest, watchlist reports) can parse
  the structure.
- Users can diff runs over time and see how the thesis evolved with
  new filings or price action.

### Negative

- Structural rigidity means small analyses look overly heavy — the
  short-form `analyze <SYM>` skill (Phase 2) still exists for
  lightweight questions; deep-research is opt-in via
  `> deep research <SYM>`.
- Persistence introduces a filesystem contract (path shape) that
  future refactors must respect or migrate.

## Rejected Alternatives

- Free-form report shape.
- JSON-only output.
- BUY/SELL/HOLD ratings.
- Auto-publish to external tools in Phase 3.

## Implementation Notes

- Deep-research skill emits markdown by default. A tiny renderer in
  `finance_mcp/research/report.py` handles:
  - Section header numbering.
  - Provenance-id → footnote linkification.
  - Evidence appendix compilation from the analyst RESULT blocks.
- Storage path template documented in the skill; the skill writes
  the file via a Hermes-provided file tool (not a new MCP tool).

## References

- ADR-0011 (provenance ids drive citations),
  ADR-0014 (analyst output supplies section content),
  ADR-0015 (RESULT blocks feed synthesizer),
  ADR-0016 (evaluator sets RESEARCH QUALITY),
  ADR-0017 (valuation section shape),
  ADR-0018 (SEC filings supply primary sources).
