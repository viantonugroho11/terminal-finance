# Phase 3 Implementation Sequence

Recommended build order once ADRs 0007–0019 are Accepted. Each step
is a small merge; do not stack unmerged work.

**Do not start implementation until the ADRs are marked Accepted.**

## Sequence

```
0. ADR review & acceptance                           (docs; this repo)
       │
       ▼
1. Provider architecture upgrade                     (ADR-0008)
   - Add tier + capabilities + name to Protocols
   - Restructure providers/ into subfolders
   - Keep Yahoo + Mock working through the new shape
       │
       ▼
2. Finance MCP gateway skeleton                      (ADR-0009)
   - New router.py stub returns the currently-registered provider
   - Move existing tools to route through it
   - Zero behavior change; tests green
       │
       ▼
3. Canonical model expansion + schema versioning     (ADR-0010)
   - Add SCHEMA_VERSION; embed in cache keys
   - New models: Filing, InsiderTrade, Institutional,
     Metric, Valuation, AnalystNote
       │
       ▼
4. Extended provenance + conflict resolution         (ADR-0011)
   - New Provenance fields (source_class, provider_tier,
     data_period, document_ref, confidence, inputs)
   - resolve_conflict() function + DataConflict block
       │
       ▼
5. Real capability-based router                      (ADR-0012)
   - Routing config file (config/finance.routing.yaml)
   - Startup validation
   - Rate-limit token bucket per provider
   - Router picks provider per call; existing tools unchanged externally
       │
       ▼
6. Quant engine package                              (ADR-0013)
   - finance_mcp/quant/ with returns, risk, technical, ratios,
     portfolio, metric
   - Migrate technical.py + calc.py under the package
     with compat re-exports
   - Fixture-based tests per module
       │
       ▼
7. Financial Datasets adapter                        (ADR-0008, 0018 dep)
   - First real second provider — proves the router + provenance
     tiering + conflict resolution end-to-end
   - Router config: statements chain becomes [financial_datasets,
     alphavantage, yahoo]
       │
       ▼
8. SEC EDGAR adapter (narrow scope)                  (ADR-0018)
   - filings index, filing_document, insider_trades, institutional
   - XBRL parser scoped to the 6 facts analysts need
   - Confirms PRIMARY_REGULATORY tier winning conflicts vs
     Financial Datasets
       │
       ▼
9. Advanced analyst skills                           (ADR-0014)
   - finance-skills/analysts/README.md (Analyst Contract)
   - fundamental, valuation, technical, risk, news-catalyst,
     competitive, lead — one PR per analyst
       │
       ▼
10. Multi-agent orchestration                        (ADR-0015)
    - finance-skills/deep-research/SKILL.md
    - Task envelope + RESULT contract; parallel subagent fan-out
    - Contradiction check in lead-analyst
       │
       ▼
11. Evaluator loop                                   (ADR-0016)
    - Rubric skill + deterministic checks module
    - Bounded 2-revision loop
    - QUALITY header always emitted
       │
       ▼
12. DCF / valuation engine                           (ADR-0017)
    - finance_mcp/valuation/ with dcf, assumptions, scenarios, comps
    - get_valuation MCP tool
    - Valuation-analyst wires it in
       │
       ▼
13. Report renderer + persistence                    (ADR-0019)
    - finance_mcp/research/report.py
    - Canonical section layout, footnote linkification,
      EVIDENCE APPENDIX
    - Save to ~/.hermes/finance/research/<SYM>/<date>-<hash>.md
       │
       ▼
14. End-to-end demo:  > deep research NVDA           (integration)
    - Real multi-provider fetch (SEC + Financial Datasets +
      Alpha Vantage or Polygon + Finnhub news)
    - Real analyst fan-out via Hermes subagents
    - Real DCF with sourced assumptions
    - Evaluator passes at ≥ MEDIUM
    - Report written to disk with EVIDENCE APPENDIX
```

## Gating rules

- Each step ends with tests green in the finance-mcp suite.
- Steps 1–2 must not change any tool's user-visible output — that is
  the safety check that the refactor did not break Phase 2 behavior.
- Steps 5, 7, 8 introduce network I/O — fixtures + `MockProvider`
  paths must remain the default for CI.
- Step 11 (evaluator) MUST land before step 14; a `deep research`
  demo without the QUALITY header is off-brand.
- ADR-0019's `RESEARCH QUALITY: LOW` header must ship visibly on
  low-quality outputs — do not soften it in the demo.

## Not in Phase 3

Deferred with their own future ADRs:

- Portfolio automation (P&L reports, tax lots, corporate actions).
- Alerts via Hermes cron (Phase 8 in original brief).
- Dedicated finance TUI.
- Redis-backed cache / multi-instance deployment.
- Monte-Carlo DCF.
- Full-XBRL parsing beyond the 6 named facts.
- PDF / HTML report renderers.
- Auto-publish to Confluence / Slack.
