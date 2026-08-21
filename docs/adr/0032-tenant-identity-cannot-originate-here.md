# ADR-0032: Tenant identity cannot originate in finance-mcp

- Status: Accepted
- Date: 2026-08-21
- Deciders: Finance Terminal team

## Context

ADR-0030 assumes finance-mcp can tell tenants apart per request:

> Telegram inbound: `tenant_id = f"tg_{tg_user_id}"`. Auto-provision on first message.

ADR-0031-era work landed the storage half of that (see the tenant_id columns
added across portfolio, watch and backtest). Wiring identity to it turned out
to be blocked, for three reasons that compound:

**1. finance-mcp has exactly one client.** Hermes is a single process serving
every Telegram user. `config/hermes.config.yaml` registers us as one static
URL (`mcp_servers.finance.url`) over one connection. From this side, every
call looks identical no matter which human caused it.

**2. The config exposes no identity forwarding.** There is no per-user header
option in the MCP server block. Adding one is a Hermes feature, and the repo's
standing constraint is explicit: *"Do not rebuild Hermes. If a capability
exists in Hermes, use it — do not add a parallel implementation here."*

**3. Headers would not be authentication anyway.** The MCP Python SDK says so
in the docstring of the very property that would carry them:

> "Headers are client-supplied input - never treat one as an identity
> assertion."

A fourth point makes the whole framing wrong rather than merely blocked: the
cron jobs (`watch_evaluate_once`, `news_ingest_once`, `morning_digest`) run on
nobody's behalf. There is no request and no user to attribute them to, so
per-request identity would not cover them even if it existed.

## Decision

**We will not invent tenant identity inside finance-mcp.** The tenant is
resolved per process (`FINANCE_TENANT`, default `local`), and any future
per-request identity must arrive from Hermes as an authenticated fact, not be
inferred from a header we chose to trust.

Consequently, code is split by whether it acts for someone:

- **Interactive paths** (tools a user triggered) read the process tenant.
- **Background paths** (cron sweeps) cross every tenant explicitly, through a
  separately named function — `watch.store.list_every_tenant()` rather than a
  flag — so that crossing a tenant boundary is visible at the call site.

## Consequences

- Positive: no security theatre. Nothing in the codebase claims to
  authenticate a tenant when it cannot.
- Positive: the storage layer is ready. When Hermes can forward an
  authenticated user, `tenant.current()` gains a request-scoped source and the
  call sites do not move.
- Negative: multi-tenant hosted mode (ADR-0030) is blocked on Hermes, not on
  us. The remaining items in its spec — quotas, fairness, admin CLI — are all
  downstream of identity and cannot be built meaningfully first.
- Negative: until then, one deployment serves one tenant. Several users means
  several deployments, each with its own `FINANCE_TENANT` and database.
- Follow-up: confirm whether Hermes can forward authenticated per-user context
  to an MCP server. That answer, not more work here, unblocks ADR-0030.

## Alternatives considered

- **Trust an `X-Finance-Tenant` header.** Rejected: the SDK explicitly warns
  against it, and anything able to reach port 7800 could set it. It would look
  like multi-tenancy while providing none.
- **Derive the tenant from the Telegram chat id in the rule's `channel`.**
  Rejected: works only for watches, and makes a delivery address double as an
  identity.
- **Fork Hermes to forward identity.** Rejected: violates the repo's founding
  constraint. Better to ask upstream for the capability.
- **One container per user.** Not rejected — this is the honest answer for a
  handful of known users today, and needs no new code.

## References

- ADR-0030 (multi-tenant hosted mode), `docs/specs/0030-multi-tenant.md`
- `config/hermes.config.yaml` — single static MCP registration
- MCP Python SDK, `mcp/server/mcpserver/context.py` — `headers` docstring
- README §Constraint — "Do not rebuild Hermes"
