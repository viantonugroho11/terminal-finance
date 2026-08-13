# ADR-0018: SEC EDGAR and primary-source integration

## Status

Accepted (Phase E landed 2026-08-13). Ships `finance_mcp/providers/sec.py`
(tier=primary, markets={US}, capabilities={sec:filings, sec:facts}) and
two MCP tools: `get_sec_filings(symbol, form_type?, limit)` +
`get_sec_facts(symbol, concept, taxonomy)`. Ticker→CIK map fetched
from https://www.sec.gov/files/company_tickers.json on first call and
cached in-process; injectable via `SecProvider(ticker_map=...)` for
tests. Requires `FINANCE_SEC_USER_AGENT` (SEC policy — bare
`"Name email@example.com"` string). Rate-limited to 10 req/sec (429
mapped to `RATE_LIMITED` with `retry_after_seconds=1`). Insider Form 4
and 13F-HR reachable via the same `sec:filings` capability with
`form_type` filter.

## Context

Yahoo and other aggregators serve derived, sometimes-stale, often
mis-unit'd financial data. For any load-bearing claim in a research
thesis (revenue, EPS, guidance, insider activity, institutional
ownership), the authoritative source is the SEC filing itself.

The Phase 3 brief §15 requires primary-source integration to prevent
Finance Hermes from relying entirely on aggregated APIs.

SEC EDGAR is free, has a documented developer API, and requires only
a compliant `User-Agent` header. Filings of interest:

- **10-K** — annual report (audited financials, MD&A, risks)
- **10-Q** — quarterly (unaudited)
- **8-K** — material events (earnings releases, guidance, M&A)
- **DEF 14A** — proxy statement (comp, governance)
- **Form 4** — insider trades
- **13F** — institutional holdings (quarterly, 45-day lag)

## Decision

We will add a **SEC adapter** as a first-class primary provider
under `finance_mcp/providers/sec/`, with its own suite of MCP tools
exposed via the gateway (ADR-0009):

```
finance.get_filings(symbol, forms?, since?, limit?)
finance.get_filing_document(accession, section?)
finance.get_insider_trades(symbol, since?)
finance.get_institutional_holdings(symbol, quarter?)
finance.get_earnings_release(symbol, latest?)         # 8-K derived
```

**Adapter design:**

- Uses SEC EDGAR REST endpoints (`data.sec.gov`) with a compliant
  `User-Agent` (contact configurable via `FINANCE_SEC_USER_AGENT`
  env — required, no default).
- Respects SEC rate limits (10 req/s per docs); token bucket in the
  adapter, coordinated with the router's budget.
- Parses filings incrementally: `filings_index → filing_metadata →
  document_sections`. XBRL parsing (financial facts extraction) is
  scoped to what the valuation and fundamental analysts need:
  `Revenue`, `NetIncome`, `EPS`, `CashAndCashEquivalents`,
  `LongTermDebt`, `SharesOutstanding`. Broader XBRL parsing added
  as skills demand.
- Returns canonical models (ADR-0010):
  - `Filing`, `InsiderTrade`, `Institutional`
  - `FinancialStatements` populated from XBRL facts where possible
    (highest provenance tier — `PRIMARY_REGULATORY`).

**Citation:** every SEC-sourced value carries `document_ref`
(accession number) and `document_url` in Provenance. Research reports
render these as inline links (ADR-0019).

**Source hierarchy interaction (ADR-0011):**

- SEC filings = `PRIMARY_REGULATORY` (tier 1). Wins conflicts by
  default.
- Financial Datasets = `STRUCTURED_DATASET` — used as a fast path for
  same fields (already-normalized XBRL) with SEC as the fallback
  authoritative source when a conflict is detected.

**Fiscal-period discipline:**

- Every extracted metric carries `data_period` (`FY2025`, `Q2 2025`)
  and the filing's `period_of_report` — never a bare year string.
- Quarterly + annual are distinguished. TTM is a `DERIVED` metric
  computed by the quant engine from the last four quarterlies, not a
  claimed primary value.

## Alternatives Considered

- **Rely on Financial Datasets alone** — it's SEC-derived so quality
  is high, but it's one provider; SEC outage or coverage gap has no
  fallback. Also, Form 4 / 13F need direct EDGAR access. Rejected as
  sole path.
- **Aggregators only, no primary** — the failure mode Phase 3 §15
  exists to prevent. Rejected.
- **Full XBRL parser out of the gate** — high complexity for
  marginal Phase 3 value. Start narrow (the facts analysts need),
  broaden when a skill needs it.
- **Wrap an existing SEC-MCP** — losing provenance/error control
  again; the SEC adapter is small enough to own.

## Consequences

### Positive

- Every DCF input and load-bearing thesis claim can trace back to a
  specific SEC accession + section.
- Insider and institutional signals become first-class research
  inputs.
- Aggregator errors on fundamentals get caught by conflict
  resolution against SEC XBRL (ADR-0011).

### Negative

- SEC filings are big and unwieldy — parsing 10-Ks is not free.
  Cache aggressively (annual filings never change once filed).
- 13F comes with a 45-day lag — must surface `as_of` clearly, not
  present it as current holdings.
- Ownership / compliance: `User-Agent` policy strictly enforced;
  operator must configure `FINANCE_SEC_USER_AGENT` on deploy.

## Rejected Alternatives

- Aggregators-only architecture.
- Financial Datasets as sole primary path.
- Wrapping external SEC-MCP.
- Full-XBRL parser in Phase 3.

## Implementation Notes

- `finance_mcp/providers/sec/` package: `client.py`, `filings.py`,
  `xbrl.py`, `insiders.py`, `holdings.py`. Lazy-imported at server
  startup (heavy dependencies confined to filing/xbrl subpaths).
- Cache TTL constants:
  - `TTL_FILINGS_INDEX = 3600` (1h — new filings appear rarely
    mid-day)
  - `TTL_FILING_DOCUMENT = 30 * 86400` (30d — filings are immutable
    once filed; conservative refresh)
  - `TTL_INSIDER = 3600`
  - `TTL_INSTITUTIONAL = 86400`
- Report renderer (ADR-0019) styles `document_url` as a clickable
  citation; text output prints the accession number.

## References

- ADR-0008 (multi-provider), ADR-0009 (gateway), ADR-0011
  (provenance / conflict), ADR-0017 (DCF consumes SEC data).
- <https://www.sec.gov/edgar/sec-api-documentation>
- <https://www.sec.gov/os/webmaster-faq#developers> (rate limits + UA)
