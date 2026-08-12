"""SQLite connection + schema bootstrap. Path from FINANCE_DB env or default."""
from __future__ import annotations
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager

_SCHEMA = Path(__file__).parent / "schema.sql"


def db_path() -> Path:
    p = os.getenv("FINANCE_DB", "/opt/data/finance/finance.db")
    path = Path(p).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), isolation_level=None)  # autocommit
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init() -> None:
    with connect() as conn:
        conn.executescript(_SCHEMA.read_text())


@contextmanager
def cursor():
    conn = connect()
    try:
        yield conn.cursor()
    finally:
        conn.close()
