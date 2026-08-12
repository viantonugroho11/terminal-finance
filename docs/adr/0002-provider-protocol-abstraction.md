# ADR-0002: Provider Protocol abstraction

- Status: Accepted
- Date: 2026-08-12
- Deciders: Finance Terminal team

## Context

The initial provider is `yfinance` (Yahoo Finance) — free, no API key,
but scraping-based and rate-limited. Users will want to swap to paid
providers (Polygon, Alpha Vantage, Financial Modeling Prep, Twelve
Data, CoinGecko) without touching MCP tool code or Hermes skills.

The Phase 2 spec explicitly requires: *"the exact provider must be
configurable"* and *"the MCP server must NOT contain provider-specific
business logic."*

## Decision

We will define three `typing.Protocol` interfaces in
`finance_mcp/providers/__init__.py` — `MarketDataProvider`,
`FundamentalProvider`, `NewsProvider` — plus a required `name: str`
attribute on every implementation for provenance. Providers return
**normalized dataclasses only** (`Quote`, `Candle`, `Company`,
`Financials`, `FinancialStatements`, `NewsItem`, `MarketOverview`,
`MarketMovers`). MCP tools depend on the Protocols, never on
provider-shaped dicts.

Provider is chosen at process start by `_pick_provider()` reading
`FINANCE_PROVIDER` env (`yahoo` | `mock`).

## Consequences

- Positive:
  - Adding Polygon = one new file (`providers/polygon.py`) + one line
    in `_pick_provider()`. Zero changes to tools, skills, config, or
    tests.
  - `MockProvider` (deterministic, seeded from `sha256(symbol)`) makes
    every server test run offline and reproducibly.
  - Normalized models are the schema seen by Hermes — no provider
    surprises leak into skills or LLM prompts.
- Negative / cost:
  - Every new field a provider might expose (e.g. `intrinsic_value`)
    requires touching the shared model — the abstraction has a
    ratcheting cost.
  - Provider-specific quirks (Yahoo's dividend-yield-as-fraction) must
    be normalized in the provider layer, not at the tool boundary.
- Follow-ups:
  - When a second real provider ships, revisit the Protocol shape and
    consider optional capability flags (e.g. `supports_intraday`).

## Alternatives considered

- **Return raw provider dicts and let skills interpret** — rejected:
  couples every skill to every provider; violates the constraint;
  makes fabrication easy because the LLM cannot tell "field missing"
  from "field named differently."
- **Abstract base classes with `NotImplementedError` stubs** — rejected:
  `Protocol` gives structural typing without inheritance, which is
  friendlier to third-party providers wrapped from external libs.

## References

- Phase 2 spec §5–§8
- `finance_mcp/providers/__init__.py`
- `finance_mcp/providers/mock.py`
- `finance_mcp/providers/yahoo.py`
- `finance_mcp/models.py`
