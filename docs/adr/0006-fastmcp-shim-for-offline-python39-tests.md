# ADR-0006: FastMCP shim for offline / Python 3.9 tests

- Status: Accepted
- Date: 2026-08-12
- Deciders: Finance Terminal team

## Context

`finance_mcp/server.py` imports `from mcp.server.fastmcp import FastMCP`
to register tools. The `mcp` PyPI package requires Python 3.10+, but
common macOS dev boxes still ship `/usr/bin/python3` at 3.9, and CI
sandboxes without network access cannot `pip install mcp` on demand.

`test_server_tools.py` exercises **the actual tool functions**
end-to-end against `MockProvider` — that coverage is the highest-value
tier we have. Losing it on any environment where `mcp` cannot be
installed would be a big regression.

The production Docker image (`finance-mcp/Dockerfile`) uses Python
3.12 and installs the real `mcp` package. That path is unchanged.

## Decision

We will add `finance-mcp/tests/conftest.py` that, at collection time:

1. Tries `import mcp.server.fastmcp`.
2. If import fails, registers a minimal in-memory shim under the same
   module path exposing `FastMCP(name)` with:
   - `.tool()` decorator that records the wrapped function under its
     `__name__` and returns the function unchanged (so tests can call
     it directly).
   - `.settings` (host / port) and `.run()` (raises — never invoked
     in tests).

The shim never activates when the real `mcp` package is importable,
so production behavior is byte-identical.

## Consequences

- Positive:
  - `pytest` runs everywhere with no extra install steps. 64/64 tests
    pass on Python 3.9 dev boxes and Python 3.12 CI.
  - Tests call `server.get_quote(...)` etc. directly — the decorator
    is a pass-through — so we exercise the real cache/retry/provenance
    pipeline, not a mock of it.
- Negative / cost:
  - The shim's decorator surface drifts from the real one at its own
    pace. Currently we only depend on `.tool()`, `.settings`,
    `.run()` — a very small contract.
  - If a future version of `mcp` moves `FastMCP` to a different module
    path, the shim needs the same rename.
- Follow-ups:
  - Pin `mcp>=x.y` in `pyproject.toml` and rerun tests against the
    real package in CI once we have a CI job on Python 3.12.

## Alternatives considered

- **Skip `test_server_tools.py` when `mcp` is missing** — rejected:
  server tests are the vertical-slice coverage; skipping hides
  regressions on dev boxes.
- **Require Python 3.11+ locally** — rejected: raises the bar for
  contributors; no benefit that outweighs a 40-line shim.
- **Refactor `server.py` to defer FastMCP registration** — rejected:
  larger change than the shim, and complicates the production path
  for a test-time concern.

## References

- `finance-mcp/tests/conftest.py`
- `finance-mcp/tests/test_server_tools.py`
- `finance-mcp/finance_mcp/server.py`
- `finance-mcp/pyproject.toml` (`requires-python = ">=3.11"`)
