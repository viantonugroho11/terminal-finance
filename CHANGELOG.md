# Changelog

All notable changes tracked here. Format loosely based on Keep-a-Changelog; project uses SemVer.

## [0.2.0] — 2026-08-13

First release covering Indonesian market support, DCF/valuation, SEC primary source, deep-research skill decomposition, and evaluator loop.

### Added — Indonesia extension (ADR-0020 / 0021 / 0022)

- `SymbolResolver` — deterministic ticker → market classifier (suffix → allowlist → crypto → default). No LLM. IDX 4-letter tickers (BBCA, TLKM, ASII, …) auto-route to IDX without a `.JK` suffix. ~330-ticker seed allowlist at `finance-mcp/finance_mcp/data/idx_tickers.txt`; refresh script at `scripts/refresh_idx_tickers.py`.
- `Router` — capability + market aware selection with tier-priority fallback chain. Config-driven via `config/finance.routing.yaml`; built-in defaults kept in sync. `Router.validate()` surfaces preference entries whose declared chain has no registered provider. `Router.call_all()` fan-out for explicit multi-source cross-verification.
- `IdxProvider` — 20 capabilities against IDX web endpoints: quote, history, company, financials (incl. banking ratios NIM/NPL/CAR/LDR/CASA), statements, dividends, corporate actions, sector, plus IDX-microstructure (foreign_flow, broker_activity, order_book, disclosures, board, shareholders, subsidiaries, IPO calendar, trading calendar, search), plus market-wide (idx_market_overview, idx_market_movers).
- `BiProvider` — Bank Indonesia macro (bi_rate, jisdor USD/IDR).
- `BpsProvider` — BPS WebAPI (gdp, cpi, inflation, unemployment). Requires `FINANCE_BPS_API_KEY`.
- `OjkProvider` — Banking SPI (NPL/CAR/NIM/LDR/credit_growth) from a locally-mirrored JSON snapshot at `FINANCE_OJK_SPI_PATH`.

### Added — US primary source (ADR-0018)

- `SecProvider` — SEC EDGAR at tier=primary for US. Capabilities: `sec:filings` (10-K/10-Q/8-K/Form 4/13F-HR) and `sec:facts` (XBRL company facts). Ticker→CIK auto-cached. Enforces SEC's User-Agent policy via `FINANCE_SEC_USER_AGENT`; 429 mapped to `RATE_LIMITED` with `retry_after=1s`.

### Added — Valuation (ADR-0017)

- `finance_mcp/valuation.py` — pure deterministic math: CAPM, WACC (with weight-sum validation), Gordon terminal, NPV, two-stage DCF, sensitivity grid, reverse-DCF via bisection. 17 reference-vector unit tests.
- Tools: `valuation_dcf`, `valuation_sensitivity`, `valuation_implied_growth`.
- Skill: `valuation-analysis` with full output template + safety rules (DCF unreliable for banks — lean on P/B).

### Added — Deep-research decomposition (ADR-0014 Steps 1–2)

Six specialist skills + one coordinator:

- `fundamental-analysis` — ratios / statements / quality / growth, with SEC cross-check
- `technical-analysis` — SMA/EMA/RSI/MACD/vol/drawdown, no pattern hallucination
- `catalyst-analysis` — news + disclosures + corp actions + SEC filings + IPO
- `peer-analysis` — sector comps with median + strengths/weaknesses vs peers
- `macro-context` — Indonesian macro block + per-equity impact
- `valuation-analysis`
- `equity-research` — coordinator composing all six per ADR-0019 template

### Added — Evaluator (ADR-0016 deterministic tier)

- `finance_mcp/evaluator.py` — pure regex + citation-graph + numeric-cross-reference rubric scorer (7 criteria, 100pt scale). Verdicts: accept (≥80), retry (60–79), low_confidence (<60). `equity-research` mandates evaluator pass before publish.
- Tool: `evaluate_report(markdown, expected_symbol?)`.

### Added — Multi-agent bridge (ADR-0015 in-process shim)

- `finance_mcp/subagents.py` — `SubagentRuntime` fan-out with bounded semaphore + per-task timeout + failure isolation. Contract (`SubagentTask`/`SubagentResult`/`FanOutReport`) stays stable when Hermes ships native subagent runtime — swap becomes runner change, not rewrite.

### Added — Envelope + provenance (ADR-0010 / 0011)

- `finance_mcp/schema.py` — `SCHEMA_VERSION` (1.2.0) + `TIER_RANK`. Every reply carries `schema_version` + `tier` in provenance.
- `Provenance` gains `resolver` (MarketContext) + `attribution` fields.
- Cache keys include market bucket so cross-market symbol collisions cannot bleed.

### Added — Deployment

- `docker-compose.yml` mounts routing YAML, passes provider toggles + credentials via env.
- `.env.example` at repo root with commentary; `.gitignore` covers real `.env`; `bootstrap.sh` auto-symlinks into `docker/`.

### Changed

- `server.py` — replaces `_pick_provider` with router-driven `_do()`; every tool goes through resolve → router → cache → retry → provenance.
- `portfolio/service.py` — router-driven (no direct Yahoo dep); `Position.currency` field; `summary()` gains `by_currency` bucket so IDR + USD do not blend.
- `finance-skills/stock-analysis` and `finance-skills/market-overview` — market-aware, Indonesian blocks, IDR formatting.
- ADR statuses: 20 of 23 Accepted; ADR-0015 marked Bridged; ADR-0016 Accepted for deterministic path (LLM loop still Proposed).

### Tests

- 211 passing (was 98 at start of session). 113 new tests across resolver, router, providers (idx/bi/bps/ojk/sec), valuation, evaluator, subagent shim, and end-to-end market routing.

### Known limitations

- IDX endpoint paths are best-guess against IDX's undocumented web-app AJAX layer — verify via `scripts/refresh_idx_tickers.py --dry-run` before relying on live data. Router falls back to Yahoo for quote/history/company/financials/statements when IDX 403s (Cloudflare). No fallback for IDX-only capabilities (foreign_flow, broker_activity, order_book, disclosures, board, shareholders, subsidiaries, ipo/trading calendar, idx_market_*) — outage = `DATA_UNAVAILABLE`, honestly surfaced.
- BPS var IDs (GDP=104, CPI=907, inflation=1905, unemployment=543) need first-call validation against your registered key.
- OJK requires operator-populated snapshot (no live scraper for XLSX).
- SEC requires `FINANCE_SEC_USER_AGENT` env — SEC policy, not our choice.
- Portfolio multi-currency: `by_currency` bucket is available; top-level `market_value` / `cost_basis` still naively sum across currencies for back-compat with pre-0.2 callers — meaningful only when the portfolio is single-currency.

## [0.1.0]

Phases 1–2 baseline. Yahoo Finance provider, portfolio SQLite, 5 skills, structured errors, deterministic technicals/calc, cache + retry + provenance envelope. 98 tests.
