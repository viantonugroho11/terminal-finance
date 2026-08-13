# ADR-0012: Capability-based provider router

## Status

Accepted (Phase B 2026-08-13 shipped `finance_mcp/router.py` +
capability/market filtering + fallback chain; Phase D 2026-08-13
lifted the preference table to `config/finance.routing.yaml` with
built-in defaults as fallback, added startup `validate()`, and exposed
`config_source` + `routing_warnings` via `cache_stats` for
diagnostics). `Router.call_all` (multi-source verification) remains
future work.

## Context

Phase 2 selects the provider at process start via `FINANCE_PROVIDER`
env. That works when there is one candidate. Phase 3 has multiple
providers with overlapping capability sets, different quality tiers
(ADR-0008), different rate limits, different costs, and different
authoritativeness (ADR-0011). Hard-coding `provider: yahoo` in the
config is exactly what the Phase 3 brief §9 forbids.

The router must decide:

1. Which provider(s) can answer this capability (`quote`, `filings`,
   `insider_trades`, `intraday_1m`, ...)?
2. Among those, which has the best quality tier for this specific
   question?
3. If we already have a fresh cached answer, return it — even if a
   higher-tier provider could theoretically improve on it (freshness
   wins within the tier's TTL).
4. On failure, try the declared fallback chain — never silently
   substitute a lower-tier answer without upgrading provenance.

## Decision

We will add `finance_mcp/router.py` with:

```python
@dataclass(frozen=True)
class Capability:
    name: str                    # "quote", "financials", "filings_10k", ...
    tier_required: str | None    # e.g. "primary" for load-bearing filings
    freshness: str               # "realtime" | "daily" | "quarterly" | "historical"

class Router:
    def register(self, provider: Provider) -> None: ...
    async def call(
        self,
        capability: str,
        *,
        symbol: str | None = None,
        prefer_tier: str | None = None,
        fetch: Callable[[Provider], Awaitable[Any]],
    ) -> tuple[Any, Provenance]:
        """Pick provider by capability → tier → declared preference →
        rate-limit budget → cost. Try fallbacks on retriable failures.
        """
```

Routing algorithm (deterministic, testable):

1. Filter registered providers to those whose `capabilities` include
   the requested capability name.
2. Sort by `(tier_priority, prefer_tier match, remaining_rate_budget,
   -cost_per_call)`. Tier priority uses the source hierarchy from
   ADR-0011.
3. Attempt in order. Each attempt uses ADR-0003 cache and ADR
   retry-with-backoff (only retryable ErrorCodes).
4. On `SYMBOL_NOT_FOUND` / `AUTHENTICATION_FAILED`, stop the fallback
   chain — those are not transient.
5. Return `(value, provenance)`. Provenance reflects the provider
   that actually served the reply.

**Configuration surface** in `config/hermes.config.yaml` — or a new
`config/finance.routing.yaml`:

```yaml
finance:
  routing:
    quote:
      preferred_tier: aggregator
      chain: [polygon, alphavantage, yahoo]
    financial_statements:
      preferred_tier: primary
      chain: [financial_datasets, sec, alphavantage]
    filings_10k:
      preferred_tier: primary
      chain: [sec]
    news:
      preferred_tier: aggregator
      chain: [finnhub, yahoo_news]
    crypto_quote:
      preferred_tier: primary
      chain: [coingecko]
```

Routing config is data, not code — swappable per deployment.

**Multi-source fetch for conflict resolution** (ADR-0011) is a
Router method (`call_all`) used only when a capability explicitly
requests cross-verification (e.g. load-bearing revenue figure in a
DCF). Not the default — cost matters.

## Alternatives Considered

- **LLM decides which provider** — inconsistent, unauditable,
  expensive. Rejected.
- **Hard-code capability→provider mapping in code** — every
  deployment tweak needs a rebuild. Rejected.
- **Random / round-robin** — ignores tier and coverage. Rejected.
- **A single "best" provider per capability, no fallback** — one
  outage sinks the tool. Rejected.

## Consequences

### Positive

- Provider outages and rate-limit trips degrade one capability at a
  time instead of taking down whole tools.
- Routing decisions are deterministic and testable (unit test the
  sort function with a fixture provider registry).
- Ops can tune preference and chains per deployment without code
  changes.
- Cost / rate-limit awareness prevents accidental blow-through of a
  free-tier quota during morning briefings.

### Negative

- Router is a load-bearing component; must stay small and boring.
- Routing config must be documented and validated on startup, or
  operators break themselves silently.
- `call_all` (multi-source verify) is expensive — must be opt-in and
  called sparingly.

## Rejected Alternatives

- LLM-adjudicated routing.
- Hardcoded provider-per-capability without fallback.
- Config-less routing (all decisions in code).

## Implementation Notes

- Router replaces `_pick_provider()`. `server.py::_do()` becomes
  `router.call(capability, symbol=..., fetch=...)`.
- Rate-limit budget starts as a simple in-process token bucket per
  provider; Redis-backed limit is future ADR if we ever go
  multi-instance.
- Routing config validated by a startup check that every referenced
  provider is registered — fail fast on typos.
- Every reply's `provenance.source` reflects the actual server, not
  the preferred one — critical for audit.

## References

- ADR-0003 (cache), ADR-0005 (errors), ADR-0008 (multi-provider),
  ADR-0011 (provenance & conflict).
