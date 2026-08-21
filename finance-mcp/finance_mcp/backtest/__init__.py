"""Backtest engine — ADR-0029.

DEVIATION FROM ADR: ADR proposed a separate `backtest-mcp` sidecar
container for isolation. v1 ships as an in-process module inside
finance-mcp for delivery speed. Boundaries kept clean (own package,
own tables, no shared state with request-path tools) so the sidecar
upgrade later is a package-move + Dockerfile add, not a rewrite.
"""
from . import context, costs, db, engine, metrics, service, strategies  # noqa: F401
