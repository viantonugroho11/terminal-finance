# ADR-0023: Alert engine + morning digest via Hermes cron + Telegram gateway

- Status: Proposed
- Date: 2026-08-14
- Deciders: Finance Terminal team

## Context

Terminal now ships 37 MCP tools, 12 skills, 7 providers. Coverage strong. Habit loop weak: no reason for a user to open the terminal (or Telegram bot from c927de4) daily unless a specific research question is in hand.

Two adjacent gaps:

- **Push, not pull.** All flows are user-initiated. Price moves, foreign-flow spikes, BI Rate changes, and earnings-day events pass silently. Retail IDX users track these manually on WhatsApp groups + broker apps.
- **Morning context.** Analysts open Bloomberg / IDNFinancials each morning for a pre-open snapshot (IHSG close, DXY, US overnight, commodities, watchlist deltas). Terminal already has every input tool — nothing composes them on a schedule.

Existing building blocks make both cheap:

- Hermes runtime provides cron.
- Telegram gateway (c927de4) already wired for outbound delivery.
- `get_quote`, `get_market_overview`, `get_foreign_flow`, `get_bi_rate`, `get_movers` already exist per ADR-0020/0022.
- Provenance wrapper (ADR-0011) already stamps every reply — reusable for alert audit trail.

Skipping this keeps the terminal a research tool with no daily surface.

## Decision

Ship two thin skills on top of existing MCP tools and Hermes cron. No new provider, no new MCP tool.

1. **`watch` skill** — user declares alert rules in natural language ("kabari kalau BBCA turun >2% atau volume >2x rata-rata 20 hari"). Skill compiles to a rule record `{symbol, metric, operator, threshold, window, channel}` persisted in `~/.hermes/finance/watches.jsonl`. A Hermes cron job (`* * * * *` market hours, hourly off-hours) evaluates rules via existing tools, fires Telegram message on trigger, respects per-rule cooldown (default 1h).

2. **`morning-digest` skill** — cron-scheduled per user timezone (default 07:30 WIB weekdays). Composes: IHSG prev close + change, top 5 IDX movers, foreign net flow top 5, US overnight (SPX/NDX), DXY + USDIDR, BI Rate + any macro release today, watchlist deltas. Renders as one Telegram message (<4096 chars) with provenance footer.

Rule store schema, evaluator loop, and digest template live in `finance-skills/watch/` and `finance-skills/morning-digest/`. Cron entries registered via Hermes `cron_jobs` config, not custom scheduler.

## Consequences

- Positive: daily-active surface without new backend. Reuses provenance, cache, retry, router unchanged. Telegram gateway earns keep. Retail IDX users get parity with paid alerting apps.
- Positive: rule store is append-only JSONL — trivial to audit, diff, back up. No DB.
- Negative: cron evaluator polls; no push from providers. Minute-granularity minimum; sub-minute spikes missed. Acceptable for retail research (not HFT).
- Negative: multi-user host (Telegram bot public) would need per-chat rule scoping + rate limit — out of scope here, tracked separately. Single-tenant only in v1.
- Negative: DeepSeek NL→rule compilation can misparse. Mitigation: skill echoes parsed rule back for confirmation before persisting.
- Follow-ups:
  - Rule DSL grammar doc in `docs/watch-dsl.md`.
  - Digest template i18n (ID + EN).
  - Cooldown + dedup tests.
  - Ops runbook entry: how to inspect / edit / disable watches.
  - Revisit when multi-tenant Telegram lands (separate ADR).

## Alternatives considered

- **Separate alert-mcp sidecar with own scheduler.** Rejected: duplicates Hermes cron, adds deploy surface, no new capability.
- **Webhook push from providers (Yahoo/IDX).** Rejected: neither exposes push. Polling is the only path.
- **Store rules in SQLite.** Rejected for v1: JSONL fits <1k rules per user, greppable, no migration cost. Revisit if multi-tenant.
- **Skip morning-digest, ship only `watch`.** Rejected: digest is the habit anchor even when no alert fires. Both together create the loop.
- **Full backtest engine first (Idea #7 from brainstorm).** Rejected: high effort, narrow audience (kuant), no daily surface. Sequence after habit loop proven.

## References

- Commit c927de4 — Hermes-native Telegram gateway.
- ADR-0011 — provenance wrapper.
- ADR-0020 — Indonesian providers.
- ADR-0022 — IDX microstructure (foreign_flow, movers).
- Brainstorm session 2026-08-14 (chat).
