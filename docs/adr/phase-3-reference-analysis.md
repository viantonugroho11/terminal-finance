# Phase 3 Reference Analysis

External projects reviewed for Phase 3 design. For each: what we
learn, what we do NOT copy, integration strategy, license posture.

Reviewed from documentation and public README only. No code was
vendored in Phase 3 design; any adoption decision must ship as its
own ADR with a fresh license and security review.

## Data-provider MCPs

### Alpha Vantage MCP

- Source: <https://github.com/alphavantage/alpha_vantage_mcp>
- Purpose: Wraps Alpha Vantage REST API as an MCP server. Broad
  coverage: quotes, fundamentals, forex, crypto, technical indicators.
- **Learn:** capability breadth of a serious retail API; per-endpoint
  rate-limit shapes; the pain of paginating fundamentals.
- **Do NOT copy:** shape of tool names (vendor-branded), lack of
  provenance envelope, no built-in cache/retry policy that matches
  our safety rules (ADR-0004, ADR-0005).
- **Integration:** none as a wrapped MCP. We build our own
  `finance_mcp/providers/alphavantage/` adapter that returns
  canonical models (ADR-0010) with our provenance (ADR-0011),
  driven by the router (ADR-0012).
- **License / cost:** Alpha Vantage API — free tier w/ 5 req/min +
  500/day; premium tiers priced. API key required (env-only,
  `FINANCE_ALPHAVANTAGE_API_KEY`).

### Financial Datasets MCP

- Source: <https://github.com/financial-datasets/mcp-server>
- Purpose: Wraps Financial Datasets API — SEC-derived normalized
  statements (income / balance / cashflow), quarterly + annual.
- **Learn:** the "SEC XBRL, but pre-normalized" seam we want between
  raw SEC (ADR-0018) and analysts (ADR-0014); tier positioning
  (`STRUCTURED_DATASET` per ADR-0011).
- **Do NOT copy:** treating it as sole primary; it's derived from
  SEC and must fall through to SEC on conflict.
- **Integration:** own adapter in
  `finance_mcp/providers/fundamentals/financial_datasets.py`,
  used as the fast path for statements; SEC EDGAR as authoritative
  fallback / conflict resolver.
- **License / cost:** commercial API; requires paid subscription for
  serious use. API key required.

### MCP FinanceX

- Source: <https://github.com/xerktech/mcp-financex>
- Purpose: Multi-source financial MCP aggregating several providers
  behind one MCP surface.
- **Learn:** the temptation to expose provider-branded tool names
  and the confusion that creates for skills — validated our
  decision to keep tools capability-named (`finance.get_quote`, not
  `finance.polygon_get_quote`).
- **Do NOT copy:** the "MCP of MCPs" pattern. That is Option B in
  ADR-0009 (rejected). Routing lives inside our gateway, not in
  Hermes' MCP config.
- **Integration:** none. Referenced as a design foil.
- **License:** review at time of any adoption (none planned).

## Multi-agent financial research

### FinRobot

- Purpose: Multi-agent framework for financial analysis using
  specialized "analyst" agents (fundamental, technical, forecasting).
- **Learn:** the *decomposition* — separating fundamental, valuation,
  technical, risk, and news into distinct agents with distinct
  contexts. Validated ADR-0014.
- **Do NOT copy:** the framework itself. We orchestrate via Hermes
  subagents (ADR-0015). The "do not rebuild Hermes" rule extends to
  "do not import a competing agent runtime."
- **Integration:** none. Concepts inform our Analyst Contract and
  RESULT block shape.

### FinSphere

- Purpose: Research-oriented multi-agent system emphasizing
  contradiction checking and multi-source fact verification.
- **Learn:** the value of an explicit contradiction pass BEFORE the
  lead writes the thesis. Fed the lead-analyst contract in ADR-0015
  ("lead runs a contradiction check across all subagent results
  before writing the thesis") and the evaluator dimensions in
  ADR-0016 (logical consistency + hallucination risk).
- **Do NOT copy:** the runtime; the source-weighting scheme (we
  prefer strict tier hierarchy over weighted scores — ADR-0011).
- **Integration:** none. Inspired the evaluator rubric.

## Common posture

- **No wholesale adoption.** Every external system reviewed here is a
  concept source, not a dependency.
- **License / vendoring.** Any future decision to include third-party
  code lands in its own ADR with:
  - License compatibility check (MIT / Apache-2.0 preferred; GPL
    only via strong scoping);
  - Security review of network calls, auth handling, secret paths;
  - Supply-chain review (pinning, provenance of the release);
  - Removal path if the upstream project stalls or forks.
- **Reference material safety.** Docs and READMEs only. No cloning
  of untrusted repositories into the workspace during design.
