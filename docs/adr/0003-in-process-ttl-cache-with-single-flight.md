# ADR-0003: In-process TTL cache with single-flight

- Status: Accepted
- Date: 2026-08-12
- Deciders: Finance Terminal team

## Context

Free market data providers (Yahoo via `yfinance` scraping) rate-limit
aggressively. A single `analyze NVDA` fans out to 5–6 tool calls; a
morning briefing hits 10+ symbols in parallel. Without caching, the
same symbol/quote is fetched dozens of times per minute and we hit
`RATE_LIMITED` quickly.

Per-domain TTLs make sense: quotes go stale in seconds, fundamentals
in hours. A durable / distributed cache (Redis) would let multiple
finance-mcp instances share state, but we only run one sidecar.

## Decision

We will implement `TTLCache` in `finance_mcp/cache.py`:

- In-process `dict` keyed by an arbitrary hashable tuple.
- Monotonic-clock expiry (`time.monotonic()`), so wall-clock skew and
  daylight saving cannot bring an expired entry back.
- `get_or_fetch(key, ttl, fetch)` **double-checks under a per-key
  `asyncio.Lock`**, so N concurrent requests for the same key trigger
  exactly one provider call (single-flight).
- Per-domain TTL constants (`TTL_QUOTE=15s`, `TTL_HISTORY=5m`,
  `TTL_FUNDAMENTALS=6h`, …) with `FINANCE_CACHE_TTL_*` env overrides.
- Returned to callers as `(value, cache_hit: bool)` so the caller can
  populate `Provenance.cache_hit` for the user-facing citation.

## Consequences

- Positive:
  - Provider load drops by roughly the fan-out width (5–10×) on hot
    symbols; the concurrent-request storm from parallel tool calls is
    collapsed to one fetch.
  - No new infra dependency; ships inside the one sidecar container.
  - Provenance surfaces cache freshness so the user knows whether a
    price is 2 s or 15 s old.
- Negative / cost:
  - Not shared across process restarts. Acceptable — sidecar restarts
    are rare and the market moves anyway.
  - Not shared across instances. Multi-instance deployment (currently
    not planned) would need a Redis-backed cache; the `TTLCache` API
    was intentionally kept small so a Redis impl can swap in behind
    the same `get_or_fetch` surface.
  - Cache lives forever within TTL — no LRU eviction. Bounded in
    practice by the small keyspace (symbols × tools).
- Follow-ups:
  - Add rough size ceiling + LRU eviction if cache size ever crosses
    a few thousand entries.

## Alternatives considered

- **No cache, rely on provider** — rejected: Yahoo rate-limits fast;
  parallel skills trip it immediately.
- **`functools.lru_cache` on provider methods** — rejected: no TTL,
  no async-safe single-flight, no visibility for `Provenance`.
- **Redis** — rejected for Phase 2: single-instance sidecar makes it
  strictly more ops for zero user-visible benefit right now.

## References

- `finance_mcp/cache.py`
- `finance_mcp/server.py:_do`
- ADR-0004 (Provenance)
