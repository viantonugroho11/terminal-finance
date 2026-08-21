"""News tables on shared finance.db. Bootstrap schema on import."""
from __future__ import annotations

from pathlib import Path

from ..portfolio.db import connect

_SCHEMA = Path(__file__).parent / "schema.sql"


def init() -> None:
    with connect() as conn:
        conn.executescript(_SCHEMA.read_text())
