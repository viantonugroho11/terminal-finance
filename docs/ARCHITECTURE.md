# Architecture

Deep-dive on how finance-mcp is built and why. For quick-start see [README](../README.md). For decision rationale see individual ADRs under [docs/adr/](adr/README.md).

## Context

Finance-mcp is a **specialized MCP sidecar** for [Hermes Agent](https://hermes-agent.nousresearch.com). Hermes handles LLM orchestration, memory, skill loading, cron, terminal I/O — this repo handles financial domain: quotes, fundamentals, valuation, macro, provenance. Hermes stays unmodified.

### Non-goals

- Not a Hermes fork.
- Not a general-purpose data warehouse (SQLite portfolio only; no OLAP).
- Not a broker integration (no order placement, no positions from external APIs — user records transactions manually).
- Not an LLM harness (no LLM math, no LLM routing).

## Runtime topology

```
┌────────────────────────────────────────────────────────────────┐
│  User                                                          │
│    │  "analisis BBCA"                                          │
│    ▼                                                           │
│  Hermes Agent  (Docker: nousresearch/hermes-agent)             │
│    ├─ SOUL.md          finance persona + safety rules          │
│    ├─ skills/          12 finance skills (auto-discovered)     │
│    └─ mcp_servers.finance → http://finance-mcp:7800/mcp        │
│                                                                │
└─────────────────────────────┬──────────────────────────────────┘
                              │  streamable-HTTP MCP
                              ▼
┌────────────────────────────────────────────────────────────────┐
│  finance-mcp  (Docker: this repo)                              │
│                                                                │
│  server.py   @mcp.tool decorators — 37 tools                   │
│      │                                                         │
│      ▼                                                         │
│  _do(tool, capability, cache_key, ttl, fetch, symbol?, market?)│
│      │                                                         │
│      ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ SymbolResolver.resolve(symbol)                          │   │
│  │   → MarketContext(market, country, currency,            │   │
│  │                    canonical_symbol, source)            │   │
│  └─────────────────────────────────────────────────────────┘   │
│      │                                                         │
│      ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ TTLCache.get_or_fetch(cache_key, ttl, fetch)            │   │
│  │   single-flight lock per key                            │   │
│  └─────────────────────────────────────────────────────────┘   │
│      │  miss                                                   │
│      ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Router.call(capability, symbol?, market?, fetch)        │   │
│  │   preference table (config/finance.routing.yaml)        │   │
│  │   filter by (capability, market)                        │   │
│  │   tier sort (primary < aggregator < scraped < mock)     │   │
│  │   fallback chain on retryable errors                    │   │
│  │   stop-codes: SYMBOL_NOT_FOUND / INVALID_SYMBOL /       │   │
│  │               AUTHENTICATION_FAILED                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│      │                                                         │
│      ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ with_retry(fn, provider, symbol)                        │   │
│  │   3 attempts; exp backoff + jitter                      │   │
│  │   retryable: TIMEOUT/RATE_LIMITED/PROVIDER_UNAVAILABLE  │   │
│  └─────────────────────────────────────────────────────────┘   │
│      │                                                         │
│      ▼                                                         │
│  ┌────────────┬────────────┬───────────┬───────────┬────────┐  │
│  │  yahoo     │   idx      │   bi      │   bps     │  ojk   │  │
│  │  scraped   │  scraped   │  primary  │  primary  │ primary│  │
│  │  US/GLOBAL │  IDX       │  MACRO    │  MACRO    │  MACRO │  │
│  │  /IDX/CRY  │            │           │  (key)    │ (snap) │  │
│  └────────────┴────────────┴───────────┴───────────┴────────┘  │
│  ┌────────────┬────────────┐                                   │
│  │  sec       │   mock     │                                   │
│  │  primary   │   mock     │                                   │
│  │  US (UA)   │   all      │                                   │
│  └────────────┴────────────┘                                   │
│      │                                                         │
│      ▼                                                         │
│  Provenance(data, source, tier, retrieved_at, cache_hit,       │
│             symbol?, resolver?, attribution?, schema_version)  │
│      │                                                         │
│      ▼                                                         │
│  {"data": <payload>, "provenance": {...}}                      │
│    OR                                                          │
│  {"error": {code, message, provider, symbol, retry_after?}}    │
└────────────────────────────────────────────────────────────────┘
```

## Module map

| Module | Responsibility |
|---|---|
| `finance_mcp/server.py` | `@mcp.tool` decorators; `_do()` is the one-and-only tool-entry orchestrator. |
| `finance_mcp/registry.py` | Process-wide `Router` singleton + `routed_quote/history/company` facades. Prevents circular imports between server.py and portfolio/. |
| `finance_mcp/router.py` | `Router` — capability + market selection, tier fallback, `call_all` fan-out. YAML-configurable. |
| `finance_mcp/resolver.py` | `SymbolResolver` — deterministic ticker → `MarketContext`. IDX allowlist file. |
| `finance_mcp/cache.py` | In-process `TTLCache` with single-flight; TTL constants per data category. |
| `finance_mcp/retry.py` | Exp-backoff-with-jitter `with_retry()`. Retryable set = {TIMEOUT, RATE_LIMITED, PROVIDER_UNAVAILABLE}. |
| `finance_mcp/errors.py` | `FinanceError` + `ErrorCode` + `classify()`. Every failure surfaces as a structured error, never a fake default. |
| `finance_mcp/models.py` | Normalized dataclasses (`Quote`, `Financials`, `MacroSeries`, `SecFactSeries`, …) + `Provenance` envelope. |
| `finance_mcp/schema.py` | `SCHEMA_VERSION` constant + `TIER_RANK` for conflict resolution. |
| `finance_mcp/technical.py` | Deterministic technicals — SMA/EMA/RSI/MACD/vol/drawdown. No LLM. |
| `finance_mcp/calc.py` | Deterministic math helpers surfaced to skills. |
| `finance_mcp/valuation.py` | Pure DCF/CAPM/WACC/sensitivity/reverse-DCF math. |
| `finance_mcp/evaluator.py` | Deterministic ADR-0016 rubric scorer for research reports. |
| `finance_mcp/subagents.py` | In-process `SubagentRuntime` fan-out shim (ADR-0015 bridge). |
| `finance_mcp/providers/` | One file per upstream: `yahoo.py`, `idx.py`, `bi.py`, `bps.py`, `ojk.py`, `sec.py`, `mock.py`. |
| `finance_mcp/portfolio/` | SQLite-backed transactions/holdings/summary/allocation/risk. Router-driven pricing. |
| `finance_mcp/logging_.py` | `tool_call` context manager — one structured log line per tool invocation. |

## Data flow, worked example

`get_quote("BBCA")`:

1. `server.get_quote("BBCA")` → `_do("get_quote", "quote", ("BBCA",), TTL_QUOTE, fetch=p.quote("BBCA"), symbol="BBCA")`.
2. `resolve_symbol("BBCA")` → `MarketContext(market="IDX", currency="IDR", canonical_symbol="BBCA.JK", source="allowlist")`.
3. Cache key = `("get_quote", "IDX", "BBCA")`. Miss.
4. `router.call("quote", symbol="BBCA")` — preference `[idx, yahoo]`; both registered; pick `idx` first.
5. `with_retry(lambda: idx.quote("BBCA"))` — idx strips `.JK`, hits IDX `GetStockSummary` endpoint via httpx.
6. Success → `Quote(symbol="BBCA.JK", price=9500, currency="IDR", ...)`.
7. Wrap in `Provenance(data=Quote, source="idx", tier="scraped", resolver={...}, attribution=None, schema_version="1.2.0")`.
8. Cache under `("get_quote", "IDX", "BBCA")` with TTL 15s. Store `(value, name, tier, attribution, resolver_dict)`.
9. Return `{"data": {...}, "provenance": {...}}`.

Failure path — IDX 403 (Cloudflare):

1. Steps 1–4 same.
2. idx.py raises `FinanceError(PROVIDER_UNAVAILABLE, "IDX blocked (HTTP 403)")`.
3. `with_retry` retries with backoff; still 403.
4. Router sees retryable code (not stop-code) → advances to `yahoo`.
5. Yahoo takes `BBCA.JK`, returns a quote in IDR.
6. Wrap with `source="yahoo"` — provenance is honest about the fallback.

## Envelope contract

Every non-error tool reply:

```json
{
  "data": {...normalized dataclass, deep-asdict'd...},
  "provenance": {
    "source": "idx",
    "schema_version": "1.2.0",
    "retrieved_at": "2026-08-13T09:22:11.482+00:00",
    "cache_hit": false,
    "tier": "scraped",
    "symbol": "BBCA",
    "resolver": {
      "market": "IDX",
      "country": "ID",
      "currency": "IDR",
      "canonical_symbol": "BBCA.JK",
      "source": "allowlist"
    },
    "attribution": "Data © IDX"
  }
}
```

Every error tool reply:

```json
{
  "error": {
    "code": "SYMBOL_NOT_FOUND",
    "message": "SEC has no CIK for ticker 'NOSUCH'",
    "provider": "sec",
    "symbol": "NOSUCH",
    "retry_after_seconds": null,
    "details": {}
  }
}
```

Skills MUST honor the envelope. See [ADR-0004](adr/0004-provenance-wrapper-on-every-tool-reply.md) and [ADR-0011](adr/0011-financial-data-provenance.md).

## Key design decisions

| # | Decision | Rationale | ADR |
|---|---|---|---|
| 1 | Streamable-HTTP MCP transport, not stdio | Hermes-in-Docker reaches finance-mcp by service name on the bridge network; stdio needs colocation. | 0001 |
| 2 | Protocol-based provider abstraction (`typing.Protocol`) | Structural typing; swap providers without inheritance; friendly to external SDK wrappers. | 0002 |
| 3 | In-process TTL cache with single-flight | Sidecar has one process; no Redis dependency. Single-flight prevents dogpile on cold cache. | 0003 |
| 4 | Provenance envelope on every reply | LLM cannot fabricate a source; downstream verifiers cite it. | 0004 |
| 5 | Structured errors with stable codes | Skills react per-code (retry, apologize, degrade) — never fake defaults. | 0005 |
| 6 | Capability + market Router (not one-provider-per-tool) | Coverage gaps in one provider stop being total failures; tier hierarchy resolves conflicts. | 0008 / 0012 |
| 7 | Symbol resolver = pure fn + curated allowlist (not LLM) | Deterministic, auditable, cheap. Wrong routes surface in provenance, not silently. | 0021 |
| 8 | YAML-configurable routing preferences | Ops can tune per-deployment without rebuild. Defaults kept in code as fallback so YAML absence never bricks the server. | 0012 |
| 9 | Every quant math in `finance_mcp/` (never in a skill) | Deterministic. Tested with reference vectors. LLM cannot silently corrupt it. | 0013 |
| 10 | Deterministic evaluator, not LLM-adjudicated | Reproducible verdicts. Rubric is falsifiable regex + citation-graph checks. | 0016 |
| 11 | In-process subagent shim, not fake Hermes runtime | Prove composition + parallelism today; native runtime is a `_run_one` swap, not a rewrite. | 0015 |
| 12 | One provider file per upstream (not one big `indonesia.py`) | BPS outage cannot kill IDX. Adapter drift stays scoped. | 0020 |

## Failure modes

| Symptom | Likely cause | Where to look |
|---|---|---|
| Every tool returns `INTERNAL` at startup | `pdb.init()` failed — DB path unwritable | `FINANCE_DB` env, container volume mount |
| IDX tools return `PROVIDER_UNAVAILABLE` consistently | Cloudflare challenge on IDX endpoints | Router falls back to Yahoo for capabilities Yahoo covers; IDX-only capabilities (foreign_flow, disclosures, …) surface DATA_UNAVAILABLE honestly |
| `AUTHENTICATION_FAILED` on `get_macro("gdp")` | `FINANCE_BPS_API_KEY` unset | `.env` or shell export |
| `AUTHENTICATION_FAILED` on `get_sec_filings` | `FINANCE_SEC_USER_AGENT` unset (SEC policy) | `.env` or shell export |
| `RATE_LIMITED` from SEC | > 10 req/sec sustained | `retry_after_seconds=1` respected; slow the caller |
| Portfolio `market_value` looks wrong for mixed IDR+USD book | Top-level fields naively sum across currencies for back-compat | Use `by_currency` bucket in `portfolio_summary` reply |
| `routing_warnings` non-empty in `cache_stats` | Preference table references a provider that isn't registered | Check `FINANCE_<PROVIDER>=off` env or missing credentials |

## Integration points

- **Hermes ↔ finance-mcp**: streamable-HTTP MCP on `http://finance-mcp:7800/mcp` (compose service name). Tool whitelist in `config/hermes.config.yaml`. Skill discovery via mounted `/opt/data/skills` volume (bootstrap symlinks `finance-skills/*`).
- **finance-mcp ↔ upstreams**: HTTPS + `httpx` per provider. Each provider owns its own `httpx.AsyncClient` (injectable for tests via `SecProvider(http=...)` / etc.).
- **finance-mcp ↔ SQLite**: `finance_mcp/portfolio/db.py` uses stdlib `sqlite3`; schema in `schema.sql`; DB path from `FINANCE_DB`, defaults to `/opt/data/finance/finance.db` inside the container.
- **finance-mcp ↔ config**: `config/finance.routing.yaml` read-only mounted at `/opt/data/config/finance.routing.yaml`.

## Growth plan

- New provider: create `providers/<name>.py` implementing the Protocols (any subset), register in `registry.build_router()`, add preference entries to `config/finance.routing.yaml`. See [RUNBOOKS](RUNBOOKS.md#add-a-new-provider).
- New capability: add constant to `providers/__init__.py`, add methods to relevant providers, add tool to `server.py`, add preference to router. See [RUNBOOKS](RUNBOOKS.md#add-a-new-capability).
- New skill: create `finance-skills/<name>/SKILL.md` following the template. Hermes auto-discovers.
- Native Hermes subagent runtime lands: swap `SubagentRuntime._run_one` for `hermes.spawn_subagent(...)`. Contract stable.
