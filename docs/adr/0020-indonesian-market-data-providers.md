# ADR-0020: Indonesian market data providers

## Status

Accepted. Phase B (`IdxProvider`, router, resolver) and Phase C
(`BiProvider`, `BpsProvider`, `OjkProvider`, `get_macro` tool) both
landed 2026-08-13. Extends ADR-0008 (multi-provider) and ADR-0011
(provenance).

## Context

The existing Finance MCP ships one real provider (`YahooProvider`,
ADR-0002). Yahoo covers Indonesian equities partially — it accepts the
`.JK` suffix for quotes and daily history, but IDX-native fundamentals
(P/E, P/B, ROE per IDX's own report), dividends, corporate actions,
IDX-IC sector taxonomy, and any macro data (BI, OJK, BPS) are either
missing, stale, or wrong-unit.

Hermes users increasingly ask about Indonesian assets ("Analisis BBCA",
"Bagaimana IHSG hari ini?", "Bagaimana pengaruh BI Rate ke bank?").
Answering these accurately requires Indonesian-native data alongside
the existing global provider, without replacing Yahoo.

Three candidate open-source projects were surveyed
(`baguskto/saham-mcp`, `NeaByteLab/IDX-API`, `nichsedge/idx-bei`) plus
official/public sources (IDX/BEI, OJK, Bank Indonesia, BPS). See
`phase-a-indonesia-findings.md` for the full matrix.

## Decision

Add Indonesian data as new **provider adapters** behind the existing
`MarketDataProvider` / `FundamentalProvider` Protocols (ADR-0002). No
parallel abstraction, no new MCP process, no wrapping of third-party
MCPs. Yahoo remains registered and continues to serve US and global
symbols.

Adapters, in the order they land:

| Order | Adapter (`finance_mcp/providers/`) | Capabilities                                 | Upstream                                     | Tier      | Auth                          |
|-------|------------------------------------|-----------------------------------------------|----------------------------------------------|-----------|-------------------------------|
| B.1   | `idx.py`                           | company, financials, dividends, corp_actions, sector | IDX endpoints (`GetStockSummary`, `GetCompanyProfiles`, `GetIssuedHistory`) via `curl_cffi` | scraped   | none                          |
| C.1   | `bi.py`                            | macro (BI Rate, JISDOR FX, inflation)        | bi.go.id HTML/CSV, scheduled fetch          | primary   | none                          |
| C.2   | `bps.py`                           | macro (GDP, CPI, unemployment)               | BPS WebAPI (JSON)                            | primary   | `FINANCE_BPS_API_KEY`         |
| C.3   | `ojk.py`                           | banking sector aggregates (NPL, CAR, NIM)    | OJK Portal Data SJK (XLSX)                   | primary   | none                          |

**IDX-primary for every Indonesian capability** (`quote`, `history`,
`company`, `financials`, `statements`, `dividends`, `corporate_actions`,
`sector`). Yahoo is the fallback for `quote` / `history` / `company` /
`financials` / `statements` so the tool degrades gracefully when
IDX's Cloudflare-protected endpoints reject us; for `dividends`,
`corporate_actions`, `sector` there is no useful Yahoo fallback and
router raises `DATA_UNAVAILABLE`. Split is in `finance_mcp/router.py`
`_PREFERENCE` table, not hard-coded in tools. Decision confirmed by
maintainer during Phase B kick-off ("kalau indo better gunakan idx").

We do **not** vendor `saham-mcp` (Node — adds runtime), `IDX-API`
(Deno — same), or `idx-bei` (would pin us to Python 3.13). We
reimplement the same public IDX endpoints in an in-tree Python adapter
so error mapping, retry, cache, and provenance stay owned by us — the
posture ADR-0008 already mandates for third-party MCPs.

### Protocol changes

Extend Provider Protocols (ADR-0008 §Decision) with:

```python
tier: Literal["primary", "aggregator", "scraped", "mock"]
capabilities: frozenset[str]      # {"quote","history","company",
                                   #  "financials","dividends",
                                   #  "corp_actions","sector",
                                   #  "macro:bi_rate", ...}
markets: frozenset[str]           # {"US","ID","GLOBAL"}
requires_api_key: bool
```

`YahooProvider` declares `markets={"US","GLOBAL","ID"}` and its
existing capability set; `IdxProvider` declares `markets={"ID"}` and
the IDX-specific capabilities. The router (ADR-0012) filters by
`(capability, market)` intersect before tier-sorting.

### Banking-specific metrics

Add optional banking fields to `Financials` (nullable, never fake):
`net_interest_margin`, `non_performing_loan_ratio`,
`capital_adequacy_ratio`, `loan_to_deposit_ratio`, `casa_ratio`,
`cost_of_credit`, `loan_growth`, `deposit_growth`. Populated only
when the provider actually returns them (idx-bei has some; OJK
aggregates cover sector-level).

### Provenance

Reuse `Provenance` dataclass as-is. `source` becomes `"idx"`,
`"bi"`, `"bps"`, `"ojk"`. Add a `license`/`attribution` string in the
provenance envelope when required (OJK, BPS).

### Cache TTLs

Reuse existing constants. Additions:

| Data                        | TTL         |
|-----------------------------|-------------|
| IDX dividends/corp actions  | 1 day       |
| IDX sector taxonomy         | 7 days      |
| BI Rate / macro daily       | 1 day       |
| BPS quarterly (GDP)         | 7 days      |
| OJK monthly (SPI)           | 1 day       |

### Legal

IDX endpoint scraping is legally the same posture as the current
`yfinance` usage: fetched per user request, short-TTL cache, no
redistribution of derived datasets. BPS/BI/OJK data is public and
carries attribution requirements the provenance envelope satisfies.

## Alternatives considered

- **Vendor `saham-mcp` as second MCP**: adds Node runtime, moves
  routing into Hermes, loses control of provenance/errors/cache.
  Rejected per ADR-0008.
- **Depend on `idx-bei` as pip package**: forces Python 3.13 across the
  service; drags Neo4j/notebook deps; upstream ToS drift affects us
  transparently. Rejected.
- **Ship one monolithic `indonesia.py` that fans out to IDX+BI+OJK+BPS**:
  couples four unrelated upstreams; a BPS outage would kill IDX. Rejected.
- **Only extend Yahoo (`.JK`) coverage**: does not solve fundamentals,
  corp-actions, or macro gaps. Rejected.

## Consequences

### Positive

- Native IDX fundamentals, sector, corp actions; native Indonesian
  macro.
- Zero change to Yahoo behavior for US/global symbols.
- Follows the router path already blueprinted in ADR-0012; each
  adapter is one file + one registry entry.
- Banking-industry ratios finally expressible in `Financials`.

### Negative

- Four new upstream failure modes to monitor.
- Scraping IDX has break risk when their endpoints or Cloudflare
  posture changes; adapter contract tests required against recorded
  fixtures.
- BPS key is a new secret to document + surface as optional.

## Implementation notes

- File layout: one module per upstream, one test module per adapter.
- Every adapter mints `FinanceError` with `provider=<self.name>` so
  existing error taxonomy (ADR-0005) is preserved end-to-end.
- No investment reasoning inside adapters — BUY/HOLD/SELL stays in
  skills (see §19 of Phase A brief).

## References

- ADR-0002 (Protocols), ADR-0008 (multi-provider), ADR-0011
  (provenance), ADR-0012 (router), ADR-0021 (market detection).
- `phase-a-indonesia-findings.md`.
- IDX/BEI, OJK, Bank Indonesia, BPS WebAPI docs.
