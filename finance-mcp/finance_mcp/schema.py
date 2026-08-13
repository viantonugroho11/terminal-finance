"""Schema versioning for the finance-mcp response envelope.

Bump SCHEMA_VERSION on any breaking change to normalized dataclasses in
`models.py` or to the Provenance envelope shape. Skills key off it to
detect wire-format drift. See ADR-0010.

Versioning discipline:
- MAJOR: field removed, renamed, or type changed.
- MINOR: new required field on an existing dataclass.
- PATCH: new optional field, new dataclass, no removal.
"""
from __future__ import annotations


SCHEMA_VERSION = "1.2.0"

# Tier ranking used both by the router and by conflict resolution in
# provenance. Lower rank wins in a conflict. See ADR-0011.
TIER_RANK = {
    "primary":    0,   # SEC, IDX, BI, BPS, OJK — issuer-published
    "aggregator": 1,   # Polygon, Alpha Vantage, Finnhub
    "scraped":    2,   # Yahoo via yfinance
    "mock":       3,   # tests only
}


def tier_rank(tier: str | None) -> int:
    return TIER_RANK.get(tier or "", 99)
