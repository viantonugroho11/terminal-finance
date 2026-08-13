# ADR-0008: Multi-provider financial data with capability tags

## Status

Accepted (Phase B–E landed 2026-08-13). All Protocols carry
`tier`, `markets`, `capabilities`, `requires_api_key`. Providers
registered: `yahoo`, `idx`, `bi`, `bps`, `ojk`, `sec`, `mock`. Router
(ADR-0012) picks per capability + market + tier; provenance envelope
(ADR-0011) surfaces the winning tier for skill-side conflict
resolution.

## Context

Phase 2 shipped one real provider (`YahooProvider`) plus `MockProvider`
for tests. Yahoo via `yfinance` is scraping-based, rate-limited,
occasionally serves stale or wrong ratios (e.g. `dividendYield` unit
drift), and offers no coverage of primary-source filings.

The Phase 3 brief lists candidate providers: Alpha Vantage, Financial
Datasets, SEC EDGAR, CoinGecko, Finnhub, Financial Modeling Prep,
Twelve Data, Polygon. Each has a different coverage matrix,
rate-limit envelope, cost, and licensing profile. If we hard-wire one
per capability we ship the same fragility we have today.

Reference MCPs to learn from (not vendor into the tree):

- Alpha Vantage MCP — <https://github.com/alphavantage/alpha_vantage_mcp>
- Financial Datasets MCP — <https://github.com/financial-datasets/mcp-server>
- MCP FinanceX — <https://github.com/xerktech/mcp-financex>

## Decision

We will keep the current `Protocol`-based abstraction (ADR-0002) and
extend every provider with a **capability declaration** and a
**quality tier**:

```python
class Provider(Protocol):
    name: str                       # "yahoo" | "polygon" | "sec" | ...
    tier: Literal["primary", "aggregator", "scraped", "mock"]
    capabilities: frozenset[str]    # e.g. {"quote", "history", "financials",
                                    #        "filings", "insider_trades"}
    rate_limit_per_min: int | None
    requires_api_key: bool
```

Router (ADR-0012) queries the capability set + tier to pick a
provider for each request, with declared fallbacks. We do NOT wrap the
external MCPs above as MCPs-of-MCPs — we borrow their coverage lists
and shape our own adapters against the underlying HTTP APIs so quality
tier, error mapping, and provenance stay ours to enforce (ADR-0011).

Initial provider roster the codebase must be able to accept in Phase 3
(actual implementation is per-provider follow-up, not this ADR):

| Provider | Tier | Primary use | API key |
|---|---|---|---|
| SEC EDGAR | primary | 10-K/10-Q/8-K, insider (Form 4), institutional (13F) | no |
| Financial Datasets | primary | normalized statements from EDGAR | yes |
| Polygon | aggregator | intraday, options, splits/dividends | yes |
| Alpha Vantage | aggregator | fundamentals + technicals fallback | yes |
| Finnhub | aggregator | news, insider sentiment | yes |
| Financial Modeling Prep | aggregator | consensus estimates, ratios | yes |
| Twelve Data | aggregator | forex + intraday equities | yes |
| Yahoo (`yfinance`) | scraped | free fallback for quote/history | no |
| CoinGecko | primary | crypto quote, market cap, dominance | no |
| Mock | mock | tests | no |

## Alternatives Considered

- **One provider per capability, hard-wired** — simplest; but any
  outage or coverage gap breaks a whole research path. Rejected.
- **Wrap every external MCP as a client and register N MCPs with
  Hermes** — moves the routing problem to Hermes; we lose control
  over provenance, retry, and cache semantics. Rejected — see ADR-0009.
- **User-configurable "provider chain" per tool** — pushes an ops
  concern to end users; discoverability terrible. Router owns this.

## Consequences

### Positive

- Coverage gaps in any single provider stop being total failures —
  router picks the next-best per capability + tier.
- Quality is a first-class field: an SEC-sourced revenue always beats
  a Yahoo-sourced revenue in conflict resolution (ADR-0011).
- Adding a provider means one adapter + one line in a registry, not a
  new MCP server.

### Negative

- Adapter drift risk: providers change response shapes; adapter tests
  must be strong (contract tests against recorded fixtures).
- API-key hygiene expands: multiple `${env:*}` vars, each with its
  own free-tier limit; ops must document all of them.
- Adapter code we own — no more "let the community MCP handle it."

## Rejected Alternatives

- Sole reliance on Yahoo / yfinance.
- Vendoring the third-party MCPs (dependency + license drag,
  provenance loss).
- Letting the LLM decide which provider to call.

## Implementation Notes

- Extend `finance_mcp/providers/__init__.py` with the capability +
  tier fields on each Protocol (Phase 3, first patch).
- `_pick_provider()` is replaced by the router in ADR-0012.
- Each new adapter lands under `finance_mcp/providers/<name>.py` with
  a matching `tests/test_<name>_provider.py` fixture suite.
- API keys read exclusively via env (`FINANCE_<PROVIDER>_API_KEY`),
  documented in the README env table.

## References

- ADR-0002 (Protocol abstraction), ADR-0010 (normalization),
  ADR-0011 (provenance), ADR-0012 (router).
- <https://www.sec.gov/os/webmaster-faq#developers> (EDGAR API terms)
- Referenced MCPs (learn from, do not vendor):
  - <https://github.com/alphavantage/alpha_vantage_mcp>
  - <https://github.com/financial-datasets/mcp-server>
  - <https://github.com/xerktech/mcp-financex>
