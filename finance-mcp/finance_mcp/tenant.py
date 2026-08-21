"""Who owns the rows this process is reading and writing.

Single-user installs never think about this: everything is `local`, which is
also what every pre-existing row was backfilled to. The indirection exists so
that hosted mode (ADR-0030) becomes a matter of setting the tenant per
request rather than threading a new argument through every call site.
"""
from __future__ import annotations

import os

DEFAULT_TENANT = "local"


def current() -> str:
    """Tenant for this process. Override with FINANCE_TENANT."""
    return os.getenv("FINANCE_TENANT", "").strip() or DEFAULT_TENANT
