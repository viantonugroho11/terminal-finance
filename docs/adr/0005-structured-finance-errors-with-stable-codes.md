# ADR-0005: Structured FinanceError with stable codes

- Status: Accepted
- Date: 2026-08-12
- Deciders: Finance Terminal team

## Context

The Phase 2 spec bans silent fake defaults on failure and requires
"useful errors to Hermes." Different failure modes need different
responses:

- `RATE_LIMITED` — back off, retry with a delay
- `TIMEOUT` / `PROVIDER_UNAVAILABLE` — retry with backoff
- `SYMBOL_NOT_FOUND` / `INVALID_SYMBOL` — do not retry; tell the user
- `AUTHENTICATION_FAILED` — do not retry; surface the ops problem
- `DATA_UNAVAILABLE` — degrade gracefully; still respond

Raw provider exceptions (`urllib3.exceptions.ReadTimeoutError`,
`yfinance` string errors, HTTP status codes buried in messages) are
useless to a skill making that decision.

## Decision

We will define `FinanceError(code: ErrorCode, message, provider,
symbol, retry_after_seconds, details)` in `finance_mcp/errors.py`
with a closed `ErrorCode` enum:

```
SYMBOL_NOT_FOUND, INVALID_SYMBOL, PROVIDER_UNAVAILABLE,
RATE_LIMITED, AUTHENTICATION_FAILED, DATA_UNAVAILABLE,
TIMEOUT, INTERNAL
```

`classify(exc, provider, symbol)` maps arbitrary exceptions into a
`FinanceError` by pattern-matching the exception name + message
(including HTTP 429 / 401 / 403 / 404 / 502 / 503, "rate limit",
"timeout", "unauthorized", "too many requests").

Providers raise `FinanceError` directly when they detect a known
condition (e.g. `quote()` raises `SYMBOL_NOT_FOUND` when
`last_price` is missing). `server._do()` catches `FinanceError` and
returns `error.to_dict()` — the tool reply becomes
`{error: {code, message, ...}}`.

`retry.py::with_retry` only retries codes in
`{TIMEOUT, PROVIDER_UNAVAILABLE, RATE_LIMITED}`. Everything else
fails fast.

## Consequences

- Positive:
  - Skills can branch on `error.code` in machine-checkable text
    (SKILL.md instructions cite the codes directly).
  - Retry policy is centrally defined — providers cannot leak "please
    keep hammering" semantics.
  - `retry_after_seconds` honors provider hints when present.
- Negative / cost:
  - `classify()` is a heuristic string match; a novel provider error
    text will fall to `INTERNAL` and not be retried. Acceptable — we
    add patterns as we see them.
  - Every provider must remember to raise `FinanceError` on known
    conditions, or the classifier gets it. Mitigated by covering
    provider methods with `try/classify(e, provider=...)`.

## Alternatives considered

- **Return HTTP-like status codes only** — rejected: throws away the
  message, and skills would still have to interpret ambiguous statuses.
- **Raw Python exceptions crossing the MCP boundary** — rejected:
  MCP JSON has no exception type; skills would receive stringified
  tracebacks and hallucinate around them.

## References

- `finance_mcp/errors.py`
- `finance_mcp/retry.py`
- `finance-skills/stock-analysis/SKILL.md` (error-code branches)
