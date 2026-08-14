# ADR-0030: Multi-tenant hosted mode (public Telegram bot)

- Status: Proposed
- Date: 2026-08-14
- Deciders: Finance Terminal team

## Context

Terminal is single-tenant Docker: one Hermes, one config, one filesystem. Telegram gateway (c927de4) works but assumes trusted operator. Opening bot publicly (e.g. `@FinanceTerminalBot`) requires:

- Per-user isolation (memory, portfolio, watches).
- Per-chat auth (bind Telegram user id → tenant id).
- Rate limits (LLM cost cap per user per day).
- Data separation on filesystem.
- Fair-share scheduling (long backtest cannot starve chat).
- Abuse controls (prompt-injection, spam).

## Decision

Introduce `tenant_id` as first-class concept. Behind feature flag `MULTI_TENANT=1`; single-tenant remains default.

1. **Identity.** Telegram user id maps to `tenant_id = tg_<user_id>`. Web/CLI auth via signed JWT (`sub = tenant_id`).
2. **Storage layout.** `~/.hermes/finance/tenants/<tenant_id>/{portfolio,watches,transcripts?}`. Shared caches (quotes, fundamentals) stay global — public data.
3. **Rate limits.** Token-bucket per tenant per (tool, LLM). Enforced in FastMCP middleware + Hermes LLM proxy. Defaults: 100 tool calls/hour, $0.50 LLM spend/day. Override per tenant via admin CLI.
4. **Scheduler fairness.** Cron per tenant runs in its own queue; global worker pool with weighted round-robin. Long jobs (backtest, transcript ingest) capped at 1 concurrent per tenant.
5. **Prompt-injection.** SOUL.md gains user-input isolation rule; Telegram inbound messages wrapped in `<user_input>` XML tag; skills instructed to treat as data.
6. **Admin.** `hermes-admin` CLI: `tenant list|create|suspend|quota`.

## Consequences

- Positive: unlocks public distribution, community bot, monetization path.
- Positive: shared cache means public data cost stays flat as users grow.
- Negative: big surface. Auth, quota, isolation, abuse — each is nontrivial.
- Negative: PII enters system (Telegram usernames, portfolio contents). Requires privacy policy, deletion endpoint, encryption-at-rest for tenant dirs.
- Negative: legal — hosting Indonesian financial data + giving analyses to public may implicate OJK / capital-markets rules. Not investment advice disclaimer required; jurisdiction review before launch.
- Follow-ups: privacy policy + ToS, DPA if EU users possible, incident-response runbook for leaked tenant data, load test to size worker pool.

## Alternatives considered

- **Stay single-tenant, ship desktop app only.** Valid path if goal is personal tool. This ADR is required only if public distribution is a goal.
- **Full SaaS rewrite (Postgres, Redis, K8s).** Rejected v1: overkill until DAU justifies. This ADR proposes minimum viable multi-tenant on existing stack.
- **Third-party auth (Auth0, Clerk).** Deferred: Telegram user id sufficient for v1; add OAuth when web UI ships.

## References

- ADR-0023 (alert engine) — assumes single-tenant; this ADR generalizes.
- Commit c927de4 (Telegram gateway).
