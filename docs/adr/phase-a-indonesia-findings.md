# Phase A — Indonesian Finance Extension: Findings

Status: research only, no code changes.
Date: 2026-08-13.

## 1. Existing Hermes / Finance architecture (as-is)

```
Hermes agent
   │
   ├─ MCP client → finance-mcp (streamable-HTTP, port 7800)
   │       ├─ providers/          (Protocol-based abstraction, ADR-0002)
   │       │     ├─ yahoo.py      (yfinance, scraped, tier="scraped")
   │       │     └─ mock.py       (deterministic, tests)
   │       ├─ server.py           (@mcp.tool, _do() = cache→retry→provider→provenance)
   │       ├─ models.py           (Quote, Company, Financials, FinancialStatements,
   │       │                       MarketOverview, Provenance)
   │       ├─ cache.py            (in-process TTL + single-flight, ADR-0003)
   │       ├─ retry.py            (backoff on retryable errors)
   │       ├─ errors.py           (FinanceError + ErrorCode, ADR-0005)
   │       ├─ technical.py, calc.py
   │       └─ portfolio/          (SQLite; transactions, holdings, risk, watchlist)
   │
   └─ Skills (finance-skills/) — auto-discovered by Hermes
         stock-analysis, market-overview, portfolio-analysis,
         crypto-analysis, risk-analysis
```

Key facts:

- Provider selection today = `FINANCE_PROVIDER` env, single provider globally
  (`server.py::_pick_provider`). Router from ADR-0012 is **proposed, not
  implemented**. Multi-provider capability tags from ADR-0008 also proposed.
- `MarketDataProvider`, `FundamentalProvider`, `NewsProvider` Protocols exist
  and are already the only surface `server.py` depends on — extension point
  is clean.
- Every tool reply wrapped in `Provenance(source, retrieved_at, cache_hit,
  symbol)` — reuse as-is for Indonesian sources.
- Cache TTLs live in `cache.py` as `TTL_QUOTE`, `TTL_HISTORY`,
  `TTL_FUNDAMENTALS`, `TTL_STATEMENTS`, `TTL_COMPANY`, `TTL_NEWS`,
  `TTL_MARKET`, `TTL_MOVERS`. Reuse.
- MCP tool surface locked in `config/hermes.config.yaml` include-list —
  new tools must be added there or Hermes will not see them.
- ADRs already cover: provider abstraction (0002), provenance (0004/0011),
  multi-provider (0008), router (0012), quant engine (0013), advanced skills
  (0014), multi-agent (0015), evaluator (0016), valuation (0017),
  SEC/primary (0018), report format (0019).

## 2. What is missing for Indonesia

1. Router (ADR-0012) not built → currently one provider process-wide.
2. Provider `capabilities` / `tier` fields (ADR-0008) not on Protocols.
3. No market detection — Yahoo works for `BBCA.JK` but not `BBCA`; and it
   has poor coverage of Indonesian fundamentals, dividends, sectors.
4. No Indonesian macro (BI, BPS, OJK).
5. No IDX sector taxonomy in skills.
6. No banking-specific ratios (NIM, NPL, CAR, LDR, CASA) in `Financials`.

## 3. External source scan

| Source        | Type          | Coverage                                                                 | Auth      | License        | Reliability / Notes                                                                                                    |
|---------------|---------------|--------------------------------------------------------------------------|-----------|----------------|------------------------------------------------------------------------------------------------------------------------|
| Saham-MCP     | Node MCP      | IHSG, quote (Yahoo passthrough), history 2019+, sector, screener        | none      | MIT            | TypeScript; wraps GitHub dataset + `yahoo-finance2` + scraping. 958 stocks. Active but small.                          |
| IDX-API       | Deno/TS repo  | OHLC, broker activity, foreign flow, corp actions, dividends, IPOs      | none      | MIT            | Direct IDX endpoints, SQLite/Drizzle. Not an MCP; would need Python port or subprocess/HTTP bridge.                    |
| idx-bei       | Python 3.13   | OHLCV, broker activity, indices, fundamentals (P/E,P/B,ROE,EPS,NPM),     | none      | MIT            | Scrapes IDX endpoints via `curl_cffi` (Cloudflare bypass). Best fundamentals coverage of the three. Requires 3.13.     |
|               |               | corp actions, disclosures                                                |           |                |                                                                                                                        |
| IDX/BEI       | Official site | Same endpoints idx-bei/IDX-API wrap                                     | none      | ToS restricts  | Cloudflare-protected. Legal grey for redistribution; personal/research OK. Break risk if endpoints change.             |
| OJK           | Portal + PDF  | SPI (NPL, CAR, NIM, credit growth), monthly                             | none      | Public data    | No API. Portal + XLSX/PDF. Manual pipeline or scheduled scrape.                                                        |
| Bank Indonesia| Web/CSV       | BI Rate, JISDOR FX, SEKI, inflation, money supply                       | none      | Public data    | No documented public API. HTML/CSV/XLSX. Some data mirrored by BPS/third-party.                                        |
| BPS           | REST API      | GDP, CPI/inflation, unemployment, trade, 549 domains                    | API key   | Public data    | Registered developer key required. JSON. Rate limits not published — treat as low.                                     |

## 4. Provider decision matrix (recommendation)

Selection criteria: license clean, active, Python-friendly, best data for
its capability, minimum surface area.

| Capability                | Primary                | Fallback         | Rationale                                                                                          |
|---------------------------|------------------------|------------------|----------------------------------------------------------------------------------------------------|
| IDX quote (real-time)     | Yahoo (`SYM.JK`)       | idx-bei scrape   | Yahoo already integrated & reliable for quotes; scrape only when Yahoo down.                       |
| IDX history (daily)       | Yahoo (`SYM.JK`)       | idx-bei          | Same — history is Yahoo's strongest suit.                                                          |
| IDX company / fundamentals| idx-bei (adapted)      | Yahoo            | Yahoo IDX fundamentals sparse; idx-bei has P/E,P/B,ROE,EPS,NPM direct from IDX.                    |
| IDX corp actions/dividends| idx-bei                | —                | Not available on Yahoo consistently.                                                               |
| IDX sector taxonomy       | idx-bei (IDX-IC)       | static map       | IDX-IC 11 sectors; embed static map as backup.                                                     |
| Banking metrics (NIM,NPL,CAR)| OJK SPI (scheduled)| bank annual reports | No API — scheduled ingest of monthly XLSX. Deferred to Phase C.                                 |
| Macro: BI Rate, FX (JISDOR)| Bank Indonesia (HTML/CSV) | BPS mirror   | Scheduled fetch, cache 1 day.                                                                       |
| Macro: GDP/CPI/unemploy   | BPS API (keyed)        | —                | Only source with a real API. Requires `FINANCE_BPS_API_KEY`.                                       |
| News                      | Yahoo (existing)       | —                | Keep. Indonesian news providers out of scope this phase.                                           |

Rejected for Phase B: Saham-MCP (Node — adds runtime + duplicates Yahoo);
IDX-API (Deno — same). We take the *approach* from idx-bei (Python +
`curl_cffi` against IDX endpoints) and write our own adapter so tier,
error mapping, and provenance stay ours (per ADR-0008).

## 5. Legal / license note

- idx-bei / IDX-API / Saham-MCP: MIT — code reuse permitted with
  attribution. We reimplement rather than vendor.
- IDX endpoint data: IDX ToS restricts redistribution. Our use = fetch on
  behalf of the user running the terminal, cache short-TTL, do not
  redistribute datasets. Same posture as existing yfinance/Yahoo usage.
- BPS API: requires developer registration; treat key as user-provided
  optional secret. Feature degrades if absent.
- OJK: public statistics; attribution advisable in provenance strings.

## 6. Deliverables in this phase

- This document.
- `docs/adr/0020-indonesian-market-data-providers.md`.
- `docs/adr/0021-market-detection-and-symbol-routing.md`.

Nothing under `finance-mcp/` or `finance-skills/` is touched.

## 7. Open decisions requiring your call before Phase B

1. Confirm the primary-vs-fallback picks in §4 (esp. Yahoo-primary for
   IDX quotes/history vs. IDX-direct-primary).
2. Confirm rebuilding an idx-bei-style adapter in-tree (Python, own
   error mapping, own cache) rather than importing idx-bei as a
   dependency. Recommended: rebuild.
3. Confirm Phase B scope = router (ADR-0012 implementation) + market
   detector + one Indonesian provider (`idx.py`), *no* macro/OJK/BPS/BI
   yet — those land in Phase C.
4. Confirm ADR-0020 and ADR-0021 numbering (next free = 0020).
