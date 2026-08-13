# Providers

Per-upstream reference. What each provider covers, what fails, what env it needs. See [ADR-0020](adr/0020-indonesian-market-data-providers.md) for the multi-provider decision and [ADR-0012](adr/0012-intelligent-provider-routing.md) for how the router selects.

## Registration matrix

| Provider | Tier | Markets | Capabilities | Auth | Env toggle |
|---|---|---|---|---|---|
| [yahoo](#yahoo) | scraped | US, GLOBAL, IDX, CRYPTO | quote, history, company, financials, statements, news, market_overview, market_movers | — | always on |
| [idx](#idx) | scraped | IDX | quote, history, company, financials, statements, dividends, corporate_actions, sector, foreign_flow, search, broker_activity, order_book, ipo_calendar, trading_calendar, disclosures, board, shareholders, subsidiaries, idx_market_overview, idx_market_movers | — | `FINANCE_IDX=on\|off` |
| [bi](#bi-bank-indonesia) | primary | MACRO | macro:bi_rate, macro:jisdor | — | `FINANCE_BI=on\|off` |
| [bps](#bps) | primary | MACRO | macro:gdp, macro:cpi, macro:inflation, macro:unemployment | `FINANCE_BPS_API_KEY` | `FINANCE_BPS=on\|off` |
| [ojk](#ojk) | primary | MACRO | macro:banking_spi | `FINANCE_OJK_SPI_PATH` | `FINANCE_OJK=on\|off` |
| [sec](#sec) | primary | US | sec:filings, sec:facts | `FINANCE_SEC_USER_AGENT` | `FINANCE_SEC=on\|off` |
| mock | mock | US, GLOBAL, IDX, CRYPTO, MACRO | all | — | `FINANCE_PROVIDER=mock` (replaces registry) |

## yahoo

Wraps `yfinance` (Python package around Yahoo Finance's public/scraped endpoints).

- **Symbol handling:** IDX symbols work with `.JK` suffix. Crypto with `-USD`. Global with market suffix (`.HK`, `.L`, `.T`).
- **Failure modes:** Yahoo silently returns nulls for many ratios on non-US listings — surfaced honestly in `Financials` (never fabricated). Occasional stale ratios (e.g. `dividendYield` unit drift → normalized).
- **Rate limit:** informal. yfinance rotates a UA and can burst; sustained > 1 req/sec starts producing empty results.
- **Router role:** primary for US/GLOBAL/CRYPTO. Fallback for IDX quote/history/company/financials/statements when `idx` fails.

## idx

In-tree Python adapter over IDX's public web endpoints (`https://www.idx.co.id/primary/...`). Same posture as `yfinance` — per-request fetch, short-TTL cache, not redistributed.

- **Endpoints hit** (all under `_BASE = "https://www.idx.co.id/primary"`):
  - `/TradingSummary/GetStockSummary` — quote + summary
  - `/StockData/GetStockHistory` — history
  - `/ListedCompany/GetCompanyProfilesDetail` — company + sector
  - `/ListedCompany/GetFinancialSummary` — ratios (incl. banking NIM/NPL/CAR/LDR/CASA)
  - `/ListedCompany/GetFinancialStatements` — 3y income/balance/cashflow
  - `/ListedCompany/GetCorporateActionDividend` — dividends
  - `/ListedCompany/GetIssuedHistory` — corp actions
  - `/TradingSummary/GetForeignFlow` — foreign flow
  - `/ListedCompany/GetCompanyProfiles` — search + security master
  - `/BrokerActivity/GetBrokerSummary` — broker activity
  - `/MarketData/GetOrderBook` — order book
  - `/NewListing/GetNewListing` — IPOs
  - `/TradingCalendar/GetCalendar` — calendar
  - `/NewsAnnouncement/GetAnnouncement` — disclosures
  - `/ListedCompany/GetBoardOfCommissionerAndDirector` — board
  - `/ListedCompany/GetShareHolder` — shareholders
  - `/ListedCompany/GetSubsidiary` — subsidiaries
  - `/StockData/GetIndexData` + `/StockData/GetSectoralSummary` — IDX overview
  - `/StockData/GetTopMovers` — IDX movers
- **Failure modes:** Cloudflare-protected. 403/503 → `PROVIDER_UNAVAILABLE`, router falls back to Yahoo for capabilities Yahoo covers. Endpoint paths are best-guess against IDX's undocumented AJAX layer — verify with `scripts/refresh_idx_tickers.py --dry-run` before production reliance. If IDX renames endpoints, patch the adapter — contract stays.
- **Transport:** httpx with browser-like UA + `X-Requested-With: XMLHttpRequest` + `Referer: idx.co.id`. Consider `curl_cffi` swap if Cloudflare rejection rate rises (adapter has an injectable `http=` seam).
- **License:** IDX ToS restricts redistribution; per-user request pattern is analogous to browser access. No dataset redistribution.

## bi (Bank Indonesia)

Bank Indonesia macro. BI does not publish a stable public REST API — this adapter hits internal JSON endpoints the public site's JS uses.

- **Endpoints** (under `https://www.bi.go.id`):
  - `/biwebservice/api/getBIRateHistory` — BI 7-Day Reverse Repo Rate history
  - `/biwebservice/api/getJisdorHistory?currency=USD` — JISDOR daily reference rate
- **Failure modes:** BI occasionally renames endpoints → `DATA_UNAVAILABLE`. No fallback.
- **Attribution:** `"Bank Indonesia"` — cite in every downstream surface.

## bps

BPS (Badan Pusat Statistik) WebAPI. Only Indonesian macro source with a real REST API.

- **Base:** `https://webapi.bps.go.id/v1/api`
- **Auth:** register at `https://webapi.bps.go.id/developer/login`, set `FINANCE_BPS_API_KEY` in env. Without it, every call fails `AUTHENTICATION_FAILED` — stop-code, router does not fall through.
- **Var IDs currently in use** (verify against your key on first call):

  | Indicator | BPS var | Unit | Freq |
  |---|---|---|---|
  | gdp | 104 | % | quarterly |
  | cpi | 907 | index | monthly |
  | inflation | 1905 | % | monthly |
  | unemployment | 543 | % | quarterly |

- **Rate limit:** not documented — treat as low. Cache is 7d for these series.
- **Attribution:** `"Badan Pusat Statistik (BPS)"`.

## ojk

Otoritas Jasa Keuangan banking-sector aggregates (SPI — Statistik Perbankan Indonesia). OJK migrated to a Portal Data SJK that publishes XLSX/PDF, **not** a REST API.

- **Model:** operator mirrors the portal to a local JSON snapshot; adapter reads that snapshot.
- **Env:** `FINANCE_OJK_SPI_PATH=/opt/data/ojk_spi.json` (mount into container).
- **Snapshot schema:**
  ```json
  {
    "_meta": {"frequency": "monthly"},
    "npl": [{"period": "2025-06", "value": 2.31, "unit": "%"}, ...],
    "car": [...],
    "nim": [...],
    "ldr": [...],
    "credit_growth": [...]
  }
  ```
- **Without the snapshot:** `get_macro("banking_spi")` returns `DATA_UNAVAILABLE` with a message pointing to the portal URL. No live scraper — XLSX parsing would rot with every OJK layout change.
- **Attribution:** `"OJK — Statistik Perbankan Indonesia"`.

## sec

SEC EDGAR — the primary source for US filings + XBRL facts.

- **Endpoints:**
  - `https://www.sec.gov/files/company_tickers.json` — ticker→CIK map (~13k entries; adapter caches in-process on first call)
  - `https://data.sec.gov/submissions/CIK{padded10digit}.json` — filings history
  - `https://data.sec.gov/api/xbrl/companyfacts/CIK{padded10digit}.json` — XBRL facts
- **Auth:** no key, but SEC policy REQUIRES a `User-Agent` identifying the caller. Set `FINANCE_SEC_USER_AGENT="Your Name your@email.com"`. Missing UA → 403 → `AUTHENTICATION_FAILED` (stop-code).
- **Rate limit:** 10 req/sec. 429 → `RATE_LIMITED` with `retry_after_seconds=1`; `with_retry` respects.
- **Ticker→CIK caching:** in-process, populated on first `sec:filings` or `sec:facts` call. Injectable via `SecProvider(ticker_map={...})` in tests.
- **Attribution:** `"U.S. Securities and Exchange Commission (EDGAR)"`.

## mock

Deterministic, seeded from `sha256(symbol)`. Set `FINANCE_PROVIDER=mock` to replace the entire registry with just `MockProvider` — enables offline test runs and hermetic CI. Covers **every** capability including macro + IDX microstructure + SEC.

## Choosing preferences

Preference table in [`config/finance.routing.yaml`](../config/finance.routing.yaml). Change without a rebuild — router reloads at startup, `cache_stats` surfaces the loaded `routing_config` path + `routing_warnings`.

Rules of thumb:
- Put **primary** tier first when it exists (SEC for US filings; BI/BPS for macro; IDX for Indonesian equities).
- Only chain fallbacks when the fallback's output shape is compatible (Yahoo can serve IDX quote via `.JK`; Yahoo cannot serve `foreign_flow`).
- Never chain across tiers with silent quality loss — provenance always names the winning provider so a skill can see what actually served the reply.

## Adding a new provider

See [RUNBOOKS.md § Add a new provider](RUNBOOKS.md#add-a-new-provider).
