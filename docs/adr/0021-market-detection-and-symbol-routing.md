# ADR-0021: Market detection and symbol-based routing

## Status

Accepted (Phase B landed 2026-08-13 — `finance_mcp/resolver.py` +
`finance_mcp/router.py` + `finance_mcp/data/idx_tickers.txt`).
Extends ADR-0012 (capability-based router).

## Context

Today the finance-mcp is provider-mono: one provider process-wide via
`FINANCE_PROVIDER` env. A user typing `"Analisis BBCA"` is served by
Yahoo, which needs `BBCA.JK` and even then returns thin IDX
fundamentals. Users should not have to spell suffixes; they type the
native ticker and expect the right provider.

ADR-0012 defines a capability-based router but does not decide how a
free-text symbol maps to a market. That is this ADR.

## Decision

Add a `SymbolResolver` — a small, deterministic, dependency-free
function that classifies a symbol into a `MarketContext(market,
country, currency, canonical_symbol)`. The router (ADR-0012) filters
providers by `(capability, market)` before tier-sorting.

### Resolution order

Given a raw symbol string:

1. **Explicit suffix** wins.
   - `SYM.JK` → `market=IDX, country=ID, currency=IDR, canonical=SYM.JK`.
   - `SYM.HK`, `SYM.L`, `SYM.T`, … → route accordingly (future).
   - Anything with no suffix falls through.
2. **IDX ticker allowlist** — a curated list of active IDX equities
   loaded at startup from `finance_mcp/data/idx_tickers.txt` (seeded
   from IDX security master; refreshable). Match is exact,
   case-insensitive, letters only, length 4 (IDX standard). Positive
   match → `market=IDX, canonical=SYM.JK` (append the `.JK` so
   downstream Yahoo calls still work when Yahoo is the chosen provider).
3. **Crypto detection** unchanged from existing usage (`BTC-USD`
   pattern, or symbol on a small crypto allowlist).
4. **Default** → `market=US, country=US, currency=USD, canonical=SYM`.

Rule 2 must be *conservative*: only tickers currently listed on IDX.
Names that collide with US tickers (e.g. `TLKM` does not collide, but
future 4-letter US listings could) are resolved by rule 1 if the user
disambiguates with a suffix. Ambiguity is logged and surfaced in
provenance (`resolver_note`).

### Data model

```python
@dataclass(frozen=True)
class MarketContext:
    market: Literal["US", "IDX", "GLOBAL", "CRYPTO"]
    country: str          # ISO 3166-1 alpha-2
    currency: str         # ISO 4217
    canonical_symbol: str # what the provider actually receives
    source: Literal["suffix", "allowlist", "crypto", "default"]

def resolve(symbol: str) -> MarketContext: ...
```

Pure function, no I/O beyond the one-shot allowlist load. Fully
unit-testable with a fixed allowlist fixture.

### Router integration

`Router.call(capability, symbol=raw, ...)` calls `resolve(raw)` first,
then filters providers by `capability ∈ provider.capabilities` **and**
`ctx.market ∈ provider.markets`. Providers pass `ctx.canonical_symbol`
downstream, not the raw string. Provenance envelope gains:

```json
"resolver": {
  "market": "IDX",
  "country": "ID",
  "currency": "IDR",
  "canonical_symbol": "BBCA.JK",
  "source": "allowlist"
}
```

Existing US flows: `resolve("AAPL") → market=US, canonical="AAPL"` —
Yahoo (declares `markets={"US","GLOBAL","ID"}`) is picked as before.
No behavior change for existing tickers.

### Refresh of the allowlist

The IDX allowlist is a text file checked into the repo. Refresh is a
script (`scripts/refresh_idx_tickers.py`, Phase B) that hits IDX's
security-master endpoint (same one `idx.py` uses) and rewrites the
file. Not automatic — an operator runs it and commits the diff, so
supply-chain risk stays visible.

## Alternatives considered

- **Ask the LLM to classify the market** — non-deterministic,
  invisible in logs, wastes tokens. Rejected.
- **Require users to always type `.JK`** — hostile UX, contradicts
  the Phase A brief §18. Rejected.
- **Fuzzy match against a name index** — expensive, ambiguous, out of
  scope. `SymbolResolver` handles tickers; company-name search remains
  a separate `search_stocks` tool.
- **Skip the allowlist, always try IDX first for 4-letter symbols** —
  breaks US 4-letter tickers (`AAPL`, `MSFT`, `TSLA` are 3–4 letters
  and share the space). Rejected.

## Consequences

### Positive

- `"Analisis BBCA"` works without any suffix from the user.
- Deterministic, testable, no LLM in the routing loop.
- Provenance shows exactly why a symbol was routed where — auditable.
- US tickers unaffected because `market=US` still selects Yahoo.

### Negative

- Allowlist has a refresh cadence — stale list means new IDX listings
  fall through to default (US) until refreshed. Operator burden.
- Rare collisions require users to disambiguate with `.JK` or `.US`
  suffix; document this.

## Implementation notes

- Lives at `finance_mcp/resolver.py`. No deps beyond stdlib.
- Allowlist file: `finance_mcp/data/idx_tickers.txt`, one ticker per
  line, comments with `#`.
- Test fixtures cover: `BBCA`, `BBCA.JK`, `AAPL`, `BTC-USD`,
  unknown-4-letter, mixed case, whitespace.
- Router integration is one call at the top of `Router.call`; existing
  `server.py::_do` becomes `router.call(capability, symbol=..., ...)`
  in the same patch that implements ADR-0012.

## References

- ADR-0012 (router), ADR-0020 (Indonesian providers),
  ADR-0002 (Protocols).
- Phase A brief §3, §18.
- IDX security master (`https://www.idx.co.id/`).
