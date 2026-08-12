# ADR-0001: HTTP MCP transport over stdio

- Status: Accepted
- Date: 2026-08-12
- Deciders: Finance Terminal team

## Context

Hermes Agent runs in the `nousresearch/hermes-agent` Docker container.
`finance-mcp` is a Python service with heavy dependencies (`yfinance`,
`pandas`, provider SDKs) that we do not want inside the Hermes image.

Per the Hermes MCP config reference, an MCP server can be registered
as either:

- `stdio` — Hermes spawns a subprocess (`command`, `args`, `env`)
- `http`  — Hermes speaks streamable-HTTP to a URL

We need Hermes-in-container to reach finance-mcp reliably.

## Decision

We will register finance-mcp with Hermes as an **HTTP MCP server** using
streamable-HTTP transport at `http://finance-mcp:7800/mcp`, deployed as
a sidecar container on the same Docker bridge network as Hermes.

`finance_mcp/server.py` calls `mcp.run(transport="streamable-http")`.
`config/hermes.config.yaml` registers it with `url` + `tools.include`.

## Consequences

- Positive:
  - Hermes image stays untouched — no Python / yfinance / pandas in it.
  - finance-mcp restarts independently of Hermes.
  - Same URL works from other clients (dashboards, ad-hoc tests) —
    useful for verification.
  - Provider swap does not require rebuilding Hermes.
- Negative / cost:
  - Two containers to keep running (docker-compose orchestrates).
  - Network hop adds ~1 ms vs stdio; irrelevant next to provider RTT.
  - Auth on the MCP endpoint is our problem to solve (currently
    unauthenticated; acceptable on the bridge network, not on public
    exposure — revisit before Phase 10).

## Alternatives considered

- **stdio subprocess inside Hermes container** — rejected: forces
  building a bespoke Hermes image containing our Python deps, breaking
  the "do not fork Hermes" constraint. Also couples restart cycles.
- **Run finance-mcp on the host, expose to Hermes via
  `host.docker.internal`** — rejected: works on Docker Desktop but not
  on Linux hosts, and complicates permissions on `~/.hermes/finance/`.

## References

- <https://hermes-agent.nousresearch.com/docs/reference/mcp-config-reference>
- `docker/docker-compose.yml`
- `config/hermes.config.yaml`
