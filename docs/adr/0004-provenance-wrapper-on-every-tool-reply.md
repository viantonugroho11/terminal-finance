# ADR-0004: Provenance wrapper on every tool reply

- Status: Accepted
- Date: 2026-08-12
- Deciders: Finance Terminal team

## Context

The Finance SOUL forbids fabrication and requires the model to say
where every number came from. If a tool reply is just the payload
(`{price: 180.42}`), the LLM has no structured way to distinguish
"live from Yahoo, 3 s old" from "cached from Yahoo, 12 s old" from
"invented from training data." Skills need a machine-checkable field
they can cite in the "SOURCES" section.

News items already carry `link` + `publisher`; market data did not.

## Decision

We will wrap every successful market/research tool reply in
`Provenance`:

```python
{
  "data": <normalized payload>,
  "provenance": {
    "source":       "yahoo" | "mock" | ...,   # provider.name
    "retrieved_at": "2026-08-12T21:04:00+00:00",
    "cache_hit":    true | false,
    "symbol":       "NVDA"                    # when applicable
  }
}
```

Skills MUST cite `provenance.source` in a `SOURCES` section and MUST
NOT strip provenance when composing tool results into their answer.

Failures return `{error: {code, message, provider, symbol,
retry_after_seconds?}}` (see ADR-0005) — never a shaped `data` block.

`Provenance.to_dict()` always calls `_deep_asdict()` so nested
dataclasses inside lists/dicts serialize cleanly.

## Consequences

- Positive:
  - The model always has a structured "where did this come from" it
    can surface to the user, closing the fabrication loophole.
  - Cache freshness leaks into the UI: users can see when a number
    was cached vs freshly fetched, which matters for volatile assets.
  - Third-party audit / replay is possible because every response
    carries a timestamp.
- Negative / cost:
  - Every reply is ~120 bytes larger. Irrelevant.
  - Skills MUST know the reply shape is `{data, provenance}` — a small
    contract added to every SKILL.md, but a real API-shape change.
  - Portfolio / watchlist tools currently do NOT wrap in Provenance
    (they read from our own SQLite; source is trivially "local"). If
    we ever pull portfolio data from a broker API, revisit.

## Alternatives considered

- **Cite provider only in prose** — rejected: puts the burden on the
  LLM to remember which tool returned which field, which is exactly
  the failure mode we want to prevent.
- **Sidecar log the model can query** — rejected: adds latency and
  a whole new tool; inline metadata is strictly simpler.

## References

- `finance_mcp/models.py::Provenance`
- `finance_mcp/server.py::_do`
- `config/SOUL.md`
- ADR-0005 (structured errors)
