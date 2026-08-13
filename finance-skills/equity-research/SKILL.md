---
name: equity-research
description: Full deep-dive equity research report — orchestrates fundamental + technical + valuation + catalyst + peer + macro-context into one ADR-0019 report. Use for "deep research on X", "full report on X", "analisis lengkap X", "research report X".
version: 0.1.0
author: Finance Hermes
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, Equity, Research, Coordinator]
    related_skills:
      - fundamental-analysis
      - technical-analysis
      - valuation-analysis
      - catalyst-analysis
      - peer-analysis
      - macro-context
    requires_tools:
      - finance.get_quote
      - finance.get_company_profile
      - finance.get_fundamentals
      - finance.get_financial_statements
      - finance.get_technical
      - finance.valuation_dcf
      - finance.valuation_sensitivity
      - finance.search_news
      - finance.get_disclosures
      - finance.get_corporate_actions
      - finance.get_sector_info
      - finance.search_stocks
      - finance.get_macro
      - finance.get_sec_filings
      - finance.get_sec_facts
      - finance.resolve_symbol_tool
---

# Equity Research (Coordinator)

Full deep-dive research report per ADR-0019 format. Composes the six
specialist skills into one output. Runs in single context today; will
fan out via Hermes subagents when the runtime ships (Phase F Step 3,
see `docs/adr/phase-f-multi-agent-plan.md`).

## When to Use

- "deep research NVDA", "full report on BBCA", "analisis lengkap TLKM"
- "research report ASII", "give me the whole picture on BBRI"

For narrower asks, delegate to the specialist skill:
- Only ratios / statements → `fundamental-analysis`
- Only chart / trend → `technical-analysis`
- Only DCF / fair value → `valuation-analysis`
- Only news / filings → `catalyst-analysis`
- Only sector comps → `peer-analysis`
- Only macro → `macro-context`

## Procedure

Execute all six analyses **in parallel** (issue all tool calls in one
turn, don't sequence). Each specialist skill's procedure is inlined
below — do not re-run their skills as sub-skills today; run their tool
calls directly. When Hermes subagents ship, replace with
`spawn_subagent(<skill-name>, <SYM>)`.

Parallel tool calls per report:

- `finance.get_quote(<SYM>)`
- `finance.get_company_profile(<SYM>)`
- `finance.get_fundamentals(<SYM>)`
- `finance.get_financial_statements(<SYM>)`
- `finance.get_technical(<SYM>, period="1y")`
- `finance.valuation_dcf(<SYM>)`
- `finance.valuation_sensitivity(<SYM>)`
- `finance.search_news(<SYM>, limit=8)`
- `finance.get_sector_info(<SYM>)`
- `finance.get_macro("bi_rate")`
- `finance.get_macro("jisdor")`
- `finance.get_macro("inflation")`

Market-conditional (check `provenance.resolver.market` from any
earlier call):

- IDX only: `get_disclosures(<SYM>, limit=10)`, `get_corporate_actions(<SYM>)`, `get_dividends(<SYM>)`, `get_foreign_flow(<SYM>)`
- US only: `get_sec_filings(<SYM>, limit=5)`, optionally `get_sec_facts(<SYM>, "Revenues")` for load-bearing cross-check

Peer set: from `get_sector_info` build a 3–8 ticker peer list via
`search_stocks(<sector>)`, then fan out `get_quote` + `get_fundamentals`
+ `get_company_profile` per peer.

## Output Format

Follow `docs/report-format-template.md` **exactly**. Section order:

1. `# <SYM> — <Company Name> — Deep Research`
2. `## Snapshot [FACT]`
3. `## Business [FACT]`
4. `## Fundamentals [FACT]` (from `fundamental-analysis` schema)
5. `## Financial Statements [FACT]`
6. `## Peer Comps [FACT + ANALYSIS]` (from `peer-analysis` schema)
7. `## Valuation [FACT + ANALYSIS]` (from `valuation-analysis` schema)
8. `## Technicals [FACT]` (from `technical-analysis` schema)
9. `## Catalysts [FACT]` (from `catalyst-analysis` schema)
10. `## Macro Context [FACT + ANALYSIS]` (from `macro-context` schema, IMPACT block anchored to this symbol)
11. `## Interpretation [ANALYSIS]`
12. `## Bull Case [ANALYSIS]`
13. `## Bear Case [ANALYSIS]`
14. `## Risks [RISK]`
15. `## Confidence [ANALYSIS]`
16. `## Sources` — numbered footnotes resolving every `[^n]` used above

Every atomic claim carries a `[^n]` citation. Sources block lists provider,
`retrieved_at`, `tier`, `attribution` from each tool's `provenance`.

## Rules

- Never re-run a specialist skill as a wrapped call — inline its tool
  set. Wrapping doubles cost and breaks parallelism today.
- Never state a number, headline, ratio, or level that did not come
  from a tool this turn.
- Never recommend buy / sell / hold. Present bull + bear + risks.
  User decides.
- Sections whose tools all errored: render `_[section unavailable]_`
  and keep going.
- Currency + market discipline:
  - IDR for `.JK` symbols; USD for US.
  - No cross-currency conversions unless user asked.
- Banking rule: for IDX bank symbols (BBCA, BBRI, BMRI, BBNI, BRIS, BJBR,
  BTPS, BNGA, NISP, PNBN, MEGA, …) DCF-on-FCF is unreliable → in
  Valuation, note this and lean on P/B + peer comps.
- Confidence discipline:
  - Low if: valuation missing FCF history, macro block half-empty, peer
    set < 3, or `provenance.tier=scraped` for load-bearing figures.
  - High if: statements from primary (idx / sec), 3+ years of history,
    peer set ≥ 5, macro complete.

## Verification

Before emitting: confirm every number in the report appears in at
least one tool result from this turn's message history. Confirm every
`[^n]` in the body resolves in Sources. If not, fix or delete the
claim.

## Fallback

If Hermes reports a tool timeout mid-report, keep the sections whose
tools returned. Emit the `[partial]` tag next to the section heading
whose source errored. Do not stall the whole report.
