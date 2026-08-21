# ADR-0026: IDX flow deep-dive — insider + institutional layer

- Status: Accepted (implemented in v0.3.0 — `providers/idx.py`, `providers/ksei.py`)
- Date: 2026-08-14
- Deciders: Finance Terminal team

## Context

ADR-0022 landed `foreign_flow` and `broker_activity` per symbol/day. Real questions from IDX users go further:

- "Broker apa yang net beli BBRI 5 hari terakhir?" (multi-day aggregation)
- "Ada insider trading di ASII bulan ini?" (KSEI + IDX disclosure)
- "Berapa % saham beredar dipegang asing sekarang?" (ownership breakdown)
- "Perubahan pemegang saham >5% minggu ini?" (regulatory disclosure)

Data lives in public IDX + KSEI endpoints:
- IDX `Disclosure/AnnouncementStock` (insider trades, %-holder changes).
- KSEI `HoldingComposition` (ownership % foreign/domestic).
- IDX `BrokerSummary` historical (already scraped per-day; aggregate missing).

## Decision

Extend `IdxProvider` + KSEI new provider `KseiProvider`. Add capabilities:

| Capability                | Method                              | Tool                          | TTL   |
|---------------------------|-------------------------------------|-------------------------------|-------|
| `insider_trades`          | `insider_trades(sym, days)`         | `get_insider_trades`          | 1h    |
| `major_holder_changes`    | `major_holder_changes(sym, days)`   | `get_major_holder_changes`    | 1h    |
| `ownership_breakdown`     | `ownership_breakdown(sym)`          | `get_ownership_breakdown`     | 1d    |
| `broker_flow_aggregate`   | `broker_flow_agg(sym, days)`        | `get_broker_flow_aggregate`   | 10min |

New skill `flow-analysis` composes foreign_flow + broker_agg + insider + ownership into one narrative per symbol.

## Consequences

- Positive: closes gap vs Stockbit / RTI Business (paid Indonesian apps).
- Positive: pure aggregation on existing raw endpoints — no new scraping tech.
- Negative: KSEI HTML fragile; needs monitoring + snapshot fallback.
- Negative: `broker_flow_aggregate` reads N days of `broker_activity` — spike in upstream calls unless cached warm. Mitigation: precompute daily during off-hours cron.
- Follow-ups: legal review of KSEI ToS for automated read; per-capability coverage test; provenance carries KSEI publication date.

## Alternatives considered

- **Client-side aggregation only.** Rejected: pushes complexity to skill layer, breaks reuse across skills.
- **Buy Stockbit/RTI feed.** Rejected: paid + not machine-readable.
- **Scrape only, no KSEI.** Rejected: ownership breakdown is load-bearing signal.

## References

- ADR-0022 (IDX microstructure).
- ADR-0012 (router).
