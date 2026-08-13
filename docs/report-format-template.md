# Deep-Research Report Format (ADR-0019)

Canonical Markdown template for skill-emitted long-form research
outputs. Every research skill (`stock-analysis`, `valuation-analysis`,
future `multi-agent-research`) MUST render its final output using this
skeleton so downstream renderers (terminal TUI, HTML export, Slack
digest) can parse a stable structure.

## Section rules

- Every section header is a level-2 `##`.
- Every atomic claim ends with a numbered citation: `[^n]`. Citations
  point to the SOURCES section.
- Every citation entry names: provider, `retrieved_at`, and (when
  present) `resolver` + `attribution` from the tool's provenance
  envelope.
- Tag each section with one of `[FACT]`, `[ANALYSIS]`, `[RISK]`,
  `[ASSUMPTION]` so the LLM's contribution is separable from tool
  output.
- Never restate provenance inline in prose — always footnote it.

## Template

```markdown
# <SYM> — <Company Name> — <Report Type>

_Generated <ISO-8601 UTC> · schema_version <X.Y.Z>_

## Snapshot [FACT]

- Price: <value> [^1]
- Market cap: <value> [^2]
- Sector / Industry: <text> [^3]

## Business [FACT]

<2-3 line summary from company profile.> [^3]

## Fundamentals [FACT]

| Metric | Value | Note |
|---|---|---|
| P/E | X.XX | [^4] |
| ROE | XX.X% | [^4] |
| ...  | ...  | ...  |

## Financial Statements [FACT]

<3y summary from get_financial_statements.> [^5]

## Valuation [FACT + ANALYSIS]

### Assumptions [ASSUMPTION]

- Discount rate: X.XX% (CAPM: rf=X% + β·ERP; β=X.X [^4])
- Growth rate: X.XX% (FCF CAGR; override: none)
- Terminal growth: X.XX%
- Projection horizon: N years

### Result [FACT]

- Enterprise value: <value> [^6]
- Equity value: <value>
- Per-share value: <value>
- Upside vs market: +/- XX.X%

### Sensitivity [FACT]

<grid from valuation_sensitivity> [^7]

## Technicals [FACT]

<SMA/EMA/RSI/MACD/volatility/drawdown block.> [^8]

## Recent Signals [FACT]

- News: [^9]
- Disclosures (IDX): [^10]
- Foreign flow (IDX, last 5d net): [^11]

## Interpretation [ANALYSIS]

- Valuation read: cheap / fair / expensive vs history + peers, cite the ratio.
- Momentum read: SMA/RSI/MACD story.
- Growth read: revenue + earnings trend.
- Quality read: margin + return-on-capital story.

## Bull Case [ANALYSIS]

- <point 1 grounded in a facted number above>
- <point 2>
- <point 3>

## Bear Case [ANALYSIS]

- <point 1>
- <point 2>
- <point 3>

## Risks [RISK]

- <specific risk tied to a metric or signal>
- <macro/regulatory risk with provenance>

## Confidence [ANALYSIS]

**Low | Moderate | High** — <one line: what would raise / lower it>

## Sources

[^1]: `finance.get_quote(<SYM>)` — provider=<X>, retrieved_at=<ISO>, tier=<Y>.
[^2]: `finance.get_company_profile(<SYM>)` — provider=<X>, ISO.
[^3]: `finance.get_company_profile(<SYM>)` — provider=<X>, ISO.
[^4]: `finance.get_fundamentals(<SYM>)` — provider=<X>, ISO, tier=<Y>.
[^5]: `finance.get_financial_statements(<SYM>)` — provider=<X>, ISO.
[^6]: `finance.valuation_dcf(<SYM>)` — deterministic (finance_mcp.valuation), inputs cited above.
[^7]: `finance.valuation_sensitivity(<SYM>)` — deterministic.
[^8]: `finance.get_technical(<SYM>)` — deterministic (finance_mcp.technical).
[^9]: `finance.search_news(<SYM>)` — provider=<X>, ISO.
[^10]: `finance.get_disclosures(<SYM>)` — provider=idx, ISO, attribution="Data © IDX".
[^11]: `finance.get_foreign_flow(<SYM>)` — provider=idx, ISO, attribution="Data © IDX".
```

## Renderer conventions

Terminal TUI:
- Tags in square brackets render as coloured labels.
- Citations render as raised superscripts, clickable to jump to Sources.
- Tables reflow via `rich.Table`.
- Sensitivity grid renders with heat-map background.

HTML export:
- `pandoc report.md -f gfm -t html5 --template=finance.tmpl` — template
  ships with the finance-mcp Docker image at `/opt/data/templates/`.

Slack digest:
- Only Snapshot + Interpretation + Confidence + top 3 sources.

## Renderer safety rules

- Never rewrite numbers to fit a narrative.
- Never omit a `[FACT]` block because it hurts the thesis.
- If a section's supporting tool errored, print `_[section unavailable — tool error]_` and continue rendering the rest.
- Citations MUST resolve — a `[^n]` with no matching source entry is a
  rendering bug, not an editorial choice.

## Versioning

Report format version = `1.0`. Bump when a section is added, renamed,
or removed — schema-consumers (TUI, HTML template) key off it.
