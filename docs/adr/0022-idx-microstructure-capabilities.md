# ADR-0022: IDX microstructure + market-wide capabilities

## Status

Accepted (Phase D landed 2026-08-13). Extends ADR-0020 (Indonesian
providers).

## Context

Phase B/C shipped IDX equity fundamentals + macro. Coverage gap
remained versus the three surveyed IDX projects (`saham-mcp`,
`IDX-API`, `idx-bei`):

- No IDX-wide market overview (IHSG, LQ45, sector performance) — the
  existing `get_market_overview` is US-only via Yahoo screener.
- No IDX movers — Yahoo's premade screener returns US symbols only.
- No foreign flow (`asing net buy/sell`) per symbol — a load-bearing
  signal for IDX analysis.
- No broker activity / order book / disclosures / IPO calendar /
  trading calendar.
- No governance data (board, shareholders, subsidiaries) that IDX
  publishes via its Listed Company endpoints.
- No name-to-ticker search — allowlist-based routing only.

These are all first-party IDX endpoints. Skipping them means every
Indonesian analysis leaves the terminal to look them up manually.

## Decision

Twelve new capabilities land on `IdxProvider`, each backed by a
public IDX web endpoint. All routed via existing `Router` per
`(capability, market="IDX")`; no fallback provider (Yahoo does not
carry these fields — router raises `DATA_UNAVAILABLE` on IDX outage
rather than silently substituting).

| Capability             | IdxProvider method       | Model                       | MCP tool                | TTL     |
|------------------------|--------------------------|-----------------------------|-------------------------|---------|
| `foreign_flow`         | `foreign_flow(sym)`      | `ForeignFlow`               | `get_foreign_flow`      | 5 min   |
| `search`               | `search(q, limit)`       | `list[SearchResult]`        | `search_stocks`         | 1 h     |
| `broker_activity`      | `broker_activity(sym,d)` | `BrokerActivity`            | `get_broker_activity`   | 10 min  |
| `order_book`           | `order_book(sym,depth)`  | `OrderBook`                 | `get_order_book`        | 10 s    |
| `ipo_calendar`         | `ipo_calendar()`         | `IpoCalendar`               | `get_ipo_calendar`      | 6 h     |
| `trading_calendar`     | `trading_calendar(y)`    | `TradingCalendar`           | `get_trading_calendar`  | 7 d     |
| `disclosures`          | `disclosures(sym, lim)`  | `DisclosureFeed`            | `get_disclosures`       | 10 min  |
| `board`                | `board(sym)`             | `Board`                     | `get_board`             | 7 d     |
| `shareholders`         | `shareholders(sym)`      | `Shareholders`              | `get_shareholders`      | 1 d     |
| `subsidiaries`         | `subsidiaries(sym)`      | `SubsidiaryList`            | `get_subsidiaries`      | 7 d     |
| `idx_market_overview`  | `idx_market_overview()`  | `IdxMarketOverview`         | `get_idx_overview`      | 1 min   |
| `idx_market_movers`    | `idx_market_movers()`    | `MarketMovers` (IDX rows)   | `get_idx_movers`        | 2 min   |

Two capability names (`idx_market_overview`, `idx_market_movers`) are
deliberately IDX-scoped instead of overloading the existing
`market_overview` / `market_movers`. Rationale: the return shape
differs (index quotes + sector perf vs. curated bucket dict), and the
existing tool contract is stable — a market-typed union would leak
routing concerns into the schema.

`MockProvider` mirrors all twelve methods with deterministic stubs so
tests exercise the full router path without network access.

### Router preference

Twelve entries added to `_PREFERENCE` (all `["idx"]`, no fallback).
Router raises `DATA_UNAVAILABLE` if the IDX chain fails — skills
surface that honestly instead of showing wrong (Yahoo) numbers.

### Coverage vs surveyed repos (post-Phase-D)

| Capability          | Ours | saham-mcp | IDX-API | idx-bei |
|---------------------|------|-----------|---------|---------|
| Quote / history     | ✓    | ✓ | ✓ | ✓ |
| Financials + bank ratios | ✓ | ✓ | ✓ | ✓ |
| Statements          | ✓    | – | ✓ | ✓ |
| Dividends / corp actions | ✓ | – | ✓ | ✓ |
| Sector info         | ✓    | ✓ | – | ✓ |
| IHSG + sector perf  | ✓    | ✓ | ✓ | ✓ |
| Movers IDX          | ✓    | ✓ | ✓ | – |
| Foreign flow        | ✓    | – | ✓ | ✓ |
| Broker activity     | ✓    | – | ✓ | ✓ |
| Order book          | ✓    | – | – | ✓ |
| IPO calendar        | ✓    | – | ✓ | – |
| Trading calendar    | ✓    | – | ✓ | – |
| Disclosures         | ✓    | – | – | ✓ |
| Board / shareholders / subsidiaries | ✓ | – | – | ✓ |
| Search              | ✓    | ✓ | ✓ | ✓ |
| Macro (BI/BPS/OJK)  | ✓    | – | – | – |

Superset. Macro coverage is unique to us.

## Alternatives considered

- **Vendor saham-mcp / IDX-API / idx-bei directly.** Rejected per
  ADR-0020 — runtime/language drag, provenance loss, error taxonomy
  mismatch.
- **Overload `get_market_overview` with a `market` param.** Rejected
  — schema union across market types leaks routing, and Hermes tool
  selection heuristics prefer distinct names.
- **Split IDX microstructure into a second `IdxMicroProvider` file.**
  Rejected — same upstream host, same headers, same auth, same
  failure modes. One provider file, one HTTP client instance.
- **Return raw HTML/CSV from the tools.** Rejected — breaks the
  normalization contract (ADR-0010) and forces skills to parse.

## Consequences

### Positive

- IDX analysis no longer forces the user out of the terminal for
  microstructure or governance data.
- Router preference stays declarative — one line per capability.
- Skills already know how to surface `provenance.attribution` and
  `provenance.resolver`; no skill-side code change needed to consume
  the new tools.

### Negative

- Endpoint paths are best-guess against IDX's undocumented web-app
  AJAX layer. Break risk on IDX redesign; adapter must recover with
  minimal-diff endpoint / field updates.
- No fallback provider for these capabilities — an IDX outage means
  the tool fails, not degrades. Documented in tool docstrings.
- Twelve extra tools in the Hermes whitelist widen the LLM's tool
  selection surface; skill prompts must be explicit about when to
  reach for the on-demand ones (order_book, broker_activity, board,
  subsidiaries) versus the default IDX bundle.

## Implementation notes

- All twelve methods live in `finance_mcp/providers/idx.py`.
- All twelve tools live in `finance_mcp/server.py`.
- `finance_mcp/data/idx_tickers.txt` expanded from ~80 to ~330 seed
  tickers. Full ~900-ticker security master requires
  `scripts/refresh_idx_tickers.py` against a live IDX endpoint.
- Tests: `tests/test_idx_extended.py` (14 unit) and
  `tests/test_idx_extended_e2e.py` (12 e2e via mock). Full suite: 148
  passed.

## References

- ADR-0020, ADR-0021, ADR-0012, ADR-0002.
- `saham-mcp`, `IDX-API`, `idx-bei` upstream repos surveyed in
  `phase-a-indonesia-findings.md`.
