# Changelog

All notable changes tracked here. Format loosely based on Keep-a-Changelog; project uses SemVer.

## [Unreleased]

Infrastructure and correctness pass, then the two remaining spec-only ADRs.
The headline is not a feature: **the test suite had not run since v0.3.0** —
a test file imported a module that ADR-0023 had moved, so pytest failed at
collection and every other test went unrun. There was no CI to notice. Adding
it surfaced three defects that were already in `main`.

All ADRs are now implemented except ADR-0030, which is blocked upstream by
ADR-0032.

### Added — Continuous integration

- `.github/workflows/ci.yml` — ruff, pytest on Python 3.11 and 3.12, and a
  Docker image build. The image job exists to catch Dockerfile/pyproject drift
  that no unit test can see; it has stayed green so far, including after
  `pypdf` was added.
- `[dev]` extra, pytest and ruff configuration. Reproducing a test run was
  previously undocumented and therefore impossible for a contributor.
- Version-drift guard: `finance_mcp.__version__` had said 0.2.0 through the
  whole 0.3.0 release. A test now fails the build if it diverges from
  `pyproject.toml`.

### Added — Licence (AGPL-3.0)

- The repo was public with no licence — all rights reserved, nobody could
  legally use or self-host it. AGPL-3.0 chosen over a permissive licence
  because hosted mode is a stated goal and the network clause is what stops a
  fork being run as a competing service.
- §13 recorded as a deliverable in `docs/specs/0030-multi-tenant.md`: a
  `/source` command and a footer link to the served commit.
- README separates licence scope from upstream data terms — the licence covers
  the code, not the market data, and IDX restricts redistribution.

### Added — Tenant key in the data layer (ADR-0030 storage half)

- `finance_mcp/migrations.py` — ordered, recorded, individually idempotent
  migrations. Nothing could previously change an existing database.
- `tenant_id` on the root tables (`accounts`, `watchlists`, `alerts`,
  `watches`, `backtest_jobs`), backfilled to `local`. Child tables reach their
  tenant through the foreign key. The news corpus stays shared — the "shared
  read pool" ADR-0030 planned to assemble from symlinks, free on one database.
- `accounts.name` and `watchlists.name` rescoped from globally `UNIQUE` to
  `UNIQUE(tenant_id, name)` via table rebuild. Cheap with one tenant's rows,
  expensive later.
- Verified against a copy of a real v0.2.0-era database: clean apply, no-op on
  re-run, `foreign_key_check` empty, `integrity_check` ok.

### Added — Untrusted-content fencing

- `finance_mcp/untrusted.py`. `news/sentiment.py` passed a raw RSS headline as
  the user turn of a classification prompt, and that label feeds the
  `sentiment_spike` alert metric — a path from anyone who can place a headline
  in an ingested feed to a user's alerts. Output validation already clamped the
  label to an enum and confidence to 0..1, so the ceiling was a flipped label,
  not arbitrary values.
- Two defences: untrusted text is fenced in delimiters it cannot break out of
  (lookalikes and control characters stripped first), and the standing
  instruction is repeated after the data.
- `SOUL.md` gains the matching rule: tool-returned text is data about the
  world, never instructions.

### Added — Multi-day broker flow (completes ADR-0026)

- `finance_mcp/flow/` — daily broker-activity snapshots keyed by
  `(symbol, date, broker_code)`, so re-running a snapshot replaces rather than
  double-counts.
- `get_broker_flow_aggregate` now honours `days`. It previously accepted the
  argument and always returned one day, because the upstream endpoint has no
  historical-date parameter — the history had to be accumulated locally.
- `IdxProvider.broker_flow_agg` removed: nothing routed to it, and it promised
  a window it structurally could not deliver.
- Cron at 17:00 WIB on trading days.

### Added — Conversational screener (ADR-0025)

- `finance_mcp/screener/` + skill `screener`. Screens a nightly snapshot;
  screening live would be 435 upstream calls per question.
- `screener/fields.py` is the security boundary. Filter fields and operators
  arrive parsed out of natural language by an LLM. Names are looked up in a
  fixed allowlist, operators matched against a fixed set, values bound as
  parameters — `order_by` included, the half that looks like formatting.
- New error code `SCREENER_FIELD_UNKNOWN`, which lists the valid fields so a
  mis-parsing caller can correct itself.
- Banking ratios (NIM, NPL, CAR, LDR, CASA) are filterable alongside the
  general metrics.

### Added — Transcript Q&A (ADR-0024)

- `finance_mcp/transcripts/` + skill `transcript-qa`. Public-expose decks
  indexed per page, searchable with citations.
- Every hit carries a 1-based page and a source URL; the skill's standing rule
  is no citation, no claim.
- Dedup by URL **and** content hash — the same deck is routinely re-filed under
  a second URL.
- Cron nightly at 03:00 WIB.

### Fixed

- `tests/test_telegram.py` imported `finance_mcp.telegram`, moved to
  `watch/telegram.py` by ADR-0023 and rewritten. The suite failed at
  collection; the "298 tests passing" badge was never true for v0.3.0.
- `tests/test_news.py` pinned fixtures to a hardcoded date against a
  `now()`-relative window. One test broke once wall-clock passed 2026-08-21;
  its neighbour had begun passing for the wrong reason — an empty window
  rather than the below-threshold path it claimed to exercise.
- `watch.eligible_now()` filtered on the process tenant, but the cron
  evaluator runs on nobody's behalf. A second tenant's watches would never
  have been looked at — no error, no log, the alert simply never arrives.
  Background sweeps now use `list_every_tenant()`.
- Three `raise` sites in `providers/yahoo.py` discarded the original exception
  inside `except`; chained with `from e`.
- Dead variable in `providers/crypto.py`; vestigial loop in `broker_flow_agg`.
- All 20 skills declared `license: MIT` while the repo is AGPL-3.0.
- README claimed 37 tools and 12 skills against an actual 78 and 20, and its
  roadmap still listed as upcoming three things that had shipped in v0.3.0.

### Deviations documented

- **ADR-0024** — filings come from the existing IDX `disclosures` feed rather
  than a hand-curated per-issuer IR scraper config, and retrieval is SQLite
  FTS5/BM25 rather than bge-m3 embeddings. The spec's stack would have put
  PyTorch in a slim image: roughly 1–2.5GB of image and ~2GB of model weights,
  against a CI image build that still completes in 16 seconds. Net new
  dependency: `pypdf`.
- **ADR-0025** — SQLite on the shared finance.db rather than DuckDB (the
  reasoning ADR-0028 already gave), and the universe is IDX only: the US
  ticker list the spec names does not exist in this repo.
- **ADR-0032 (new)** — tenant identity cannot originate in finance-mcp. Hermes
  is a single process registered as one static MCP URL, its config exposes no
  per-user forwarding, adding that is a Hermes change the repo's founding
  constraint forbids, and the MCP SDK warns that headers are never an identity
  assertion. The cron jobs settle it: they run on nobody's behalf. ADR-0030
  moves to *Blocked by ADR-0032*, its storage half done.

### Known limitations

- Neither the screener nor transcript ingest has touched live data — every
  test is offline by design. Whether IDX issuers file public-expose decks
  consistently enough for ADR-0024 to be useful is still unproven;
  `transcript_coverage` will report the truth per issuer after the first
  nightly run.
- Multi-tenant serving remains one deployment per tenant until Hermes can
  forward authenticated per-user context.

### Counts

- MCP tools: 78 → **86** (verified against the `@mcp.tool()` declarations).
- Skills: 20 → **22** (`screener`, `transcript-qa`).
- Tests: **0 runnable → 378**, green on Python 3.11 and 3.12.
- ADRs: 31 → **32**; none now sit in an unexplained "proposed" state.

## [0.3.0] — 2026-08-14

Second release. Adds daily habit loop (alerts + morning digest), news + sentiment layer, IDX flow deep-dive (insider, institutional, KSEI ownership), lot-tracked portfolio with Indonesian tax + rebalance, deterministic backtest engine, and crypto + forex expansion (Binance/Indodax multi-venue, Coinglass derivatives, JISDOR + CIP forwards). 9 ADRs written; 6 implemented; 3 spec-only (transcripts, screener, multi-tenant).

Roadmap references: `docs/adr/0023..0031`, `docs/specs/0023..0031`.

### Added — Alert engine + morning digest (ADR-0023)

- `finance_mcp/watch/` — Rule dataclass, SQLite-backed store, cooldown-aware evaluator, metric resolvers (quote change, volume vs MA20, foreign net flow, sentiment spike from ADR-0028), Telegram delivery helper with env gate + Markdown message rendering.
- `finance_mcp/digest.py` — deterministic pre-open composer: IHSG, US overnight (SPX/NDX), FX (DXY/USDIDR), BI Rate, IDX movers, foreign flow, watchlist. Bilingual ID/EN via `DIGEST_LANG`; enforces Telegram 4096-char cap.
- Tools: `watch_add`, `watch_list`, `watch_pause`, `watch_resume`, `watch_delete`, `watch_evaluate_once`, `morning_digest`. Two-step NL rule creation (parse → confirm → persist).
- Cron: 1-min evaluator WIB market hours, 15-min off-hours, 07:30 WIB weekday digest.
- Skills: `watch`, `morning-digest`.
- Audit trail JSONL sidecar at `$FINANCE_DB_DIR/watches.audit.jsonl`.

### Added — News + sentiment layer (ADR-0028)

- `finance_mcp/news/` — RSS ingest with stdlib `ElementTree` parser (no feedparser dep). 6 sources v1: Kontan, Bisnis, IDNFinancials, Reuters biz, CNBC markets, IDX press.
- Symbol tagger — precision-first regex + word-boundary aliases from `data/symbol_aliases.yaml`.
- Sentiment worker — DeepSeek zero-shot classifier (via OpenAI-compatible HTTP) with lexicon-only fallback for offline runs.
- SQLite-backed article + sentiment store; aggregate score/summary queries with min-5-articles guard.
- Tools: `news_ingest_once`, `news_score_missing`, `get_news`, `news_sentiment`.
- Cron: 15-min ingest, 20-min sentiment scoring.
- Alert integration: watch metric `sentiment_spike` wired to news store (24h window).
- Skill: `news-brief`.

### Added — IDX flow deep-dive (ADR-0026)

- `providers/idx.py` — new methods on `IdxProvider`: `insider_trades(sym, days)`, `major_holder_changes(sym, days)`, `broker_flow_agg(sym, days)`. Parses best-effort IDX endpoints; tolerates missing fields.
- `providers/ksei.py` — new `KseiProvider` for ownership breakdown. CSV parser tolerates two field-name spellings; fetcher injectable. `FINANCE_KSEI` env gate.
- Models: `InsiderTrade[List]`, `HolderChange[List]`, `OwnershipBreakdown`, `BrokerAggRow`, `BrokerFlowAggregate`.
- Tools: `get_insider_trades`, `get_major_holder_changes`, `get_broker_flow_aggregate`, `get_ownership_breakdown`.
- Skill: `flow-analysis` — composed "smart money" narrative per symbol.

### Added — Portfolio lot-tracking + Indonesian tax + rebalance (ADR-0027)

- `portfolio/lots_schema.sql` — `lots` (buy) + `lot_closes` (sell links) tables. Coexists with running-avg `transactions`; independent stores.
- `portfolio/lots.py` — `Lot` / `Close` CRUD + FIFO / LIFO / HIFO matching. Sells validated against open qty; short refused.
- `portfolio/tax.py` — `Regime` constants: **ID** (0.1% equity sell PPh, 10% dividend, 0.11% + 0.11% PPN crypto both sides) and **US** (zero, capital gains reported separately). References: DGT PMK 34/2017, PMK 68/2022.
- `portfolio/lots_calc.py` — pure `unrealized_pnl(quotes)` + `realized_pnl(regime)`. Missing quotes surface as null price, never substituted.
- `portfolio/rebalance.py` — deterministic weight-diff plan with tolerance + per-trade tax cost. (ADR called for LP via scipy — deferred; upgrade path clear.)
- Tools: `record_trade`, `list_lots`, `get_unrealized_pnl`, `get_realized_pnl`, `rebalance_plan`. Live quote fallback when caller omits `quotes`.
- Skill: `portfolio-rebalance` — strict "never call `record_trade` without confirmation", "always show tax cost per sell".
- Migration: `scripts/migrate_portfolio_v1_to_v2.py` — one-shot copy running-avg positions into synthetic buy lots (idempotent, symbol-scoped).

### Added — Backtest engine (ADR-0029, in-process v1)

- `finance_mcp/backtest/` — separate package with own SQLite tables, no shared state with request-path tools.
- **DEVIATION** from ADR: shipped in-process rather than sidecar container; upgrade to sidecar = package-move + Dockerfile add. Sync execute in v1; poll API in place for async upgrade.
- `context.py` — `BarContext` enforces no-look-ahead: `prices(lookback)` slices past+current only; `future(offset)` raises `LookAheadError`.
- `costs.py` — per-market `CostModel` (ID: 0.15% comm + 5bps slippage + 0.1% PPh sell; US: $0.005/share + 2bps; CRYPTO: 0.1% + 3bps).
- `strategies.py` — registry: `buy_and_hold`, `sma_cross`, `mean_revert`. Deterministic pure functions.
- `engine.py` — bar-by-bar loop; fills at NEXT bar open (never same-bar close); MtM at each close.
- `metrics.py` — `total_return`, `max_drawdown`, `sharpe`, `sortino`, `hit_rate`, `summarize`. Returns `None` where undefined (zero-variance sharpe = null, not 0).
- `service.py` — job store + sync `execute`.
- Tools: `list_strategies`, `submit_backtest`, `get_backtest_status`, `get_backtest_result`.
- Skill: `backtest` — strict "no future extrapolation", "sharpe null means null".

### Added — Crypto + forex expansion (ADR-0031)

- **DEVIATION** from ADR: shipped without `ccxt` dep. Direct httpx to Binance + Indodax public REST. Kraken/Coinbase deferred.
- `providers/crypto.py` — `CryptoProvider`. Capabilities: `crypto_ohlcv_venue`, `crypto_orderbook`, `stablecoin_peg`. Binance klines/depth/ticker + Indodax TV-format candle parser. USDT/USDC quote fallback for peg lookup. Fetcher-injectable for offline tests.
- `providers/coinglass.py` — `CoinglassProvider`. Capabilities: `crypto_funding`, `crypto_open_interest`. Optional `COINGLASS_API_KEY` promotes to paid tier; 429 → `RATE_LIMITED` with hint.
- `providers/bi.py` — extend with `jisdor_rate(date=None)` single-value convenience.
- `calc.py` — `fx_forward_via_cip`: covered interest parity forward + points. Configurable day-count (default 360). Raises on invalid inputs.
- Models: `CryptoCandle`, `CryptoOhlcv`, `CryptoOrderBook[Level]`, `PerpFunding`, `PerpOpenInterest`, `StablecoinPeg`, `FxCross`, `JisdorRate`, `FxForward`.
- Tools: `get_crypto_ohlcv`, `get_crypto_orderbook`, `get_stablecoin_peg`, `get_perp_funding`, `get_perp_oi`, `get_fx_cross`, `get_jisdor_rate`, `get_fx_forward`. Forward output flagged `derived: true` + `method: "cip"` — never confused with tradable dealer quote.
- Skills: `crypto-deep` (composes spot + venue spread + funding + OI + peg), `fx-analysis` (composes spot + JISDOR + forward via CIP).
- Env gates: `FINANCE_CRYPTO`, `FINANCE_COINGLASS` (default on).

### Added — Documentation

- 9 ADRs: `docs/adr/0023..0031`.
- 9 matching specs with user stories, deliverables per file, success conditions, milestones + effort estimate: `docs/specs/0023..0031`.

### Deviations documented

- **ADR-0028 → SQLite** (spec said DuckDB) — reuses `portfolio.db`; documented in schema comment.
- **ADR-0029 → in-process** (spec said sidecar container) — package boundary clean for later split.
- **ADR-0031 → no ccxt** — direct httpx to Binance + Indodax.
- **ADR-0027 → weight-diff rebalance** (spec said LP via scipy) — deterministic, upgrade path clear.

### Spec-only (not yet implemented)

- ADR-0024 IDX earnings transcript Q&A — needs `bge-m3` embedding model + `pdfplumber` ingest.
- ADR-0025 conversational screener — needs DuckDB snapshot job over 8k+ universe.
- ADR-0030 multi-tenant hosted mode — gated on public bot demand.

### Counts

- MCP tools: 37 → **78** (+41)
- Skills: 12 → **20** (+8)
- Providers: 7 → **9** (+2: KseiProvider, CryptoProvider, CoinglassProvider; -0)
- Tests: 211 → **298** (+87 across watch, news, digest, ksei, idx_flow, lots, backtest, crypto_forex)

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
