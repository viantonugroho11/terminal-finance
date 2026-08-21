"""Migrations must upgrade a v0.3.0-shaped database without losing rows.

Every other test builds its database from the current schema.sql, so it
proves nothing about existing installs. These tests construct the *old*
shape by hand, put rows in it, migrate, and check the data survived.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest

# Each test gets its own database file; set before importing the modules that
# read FINANCE_DB at call time.
os.environ.setdefault(
    "FINANCE_DB", tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
)

from finance_mcp import migrations  # noqa: E402
from finance_mcp.portfolio.db import connect  # noqa: E402

# The v0.3.0 schema, before tenant_id existed.
OLD_SCHEMA = """
CREATE TABLE accounts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    currency   TEXT NOT NULL DEFAULT 'USD',
    kind       TEXT NOT NULL DEFAULT 'brokerage',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    symbol      TEXT NOT NULL,
    side        TEXT NOT NULL,
    quantity    REAL NOT NULL,
    price       REAL NOT NULL,
    fee         REAL NOT NULL DEFAULT 0,
    currency    TEXT NOT NULL DEFAULT 'USD',
    executed_at TEXT NOT NULL,
    note        TEXT
);
CREATE TABLE watchlists (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE alerts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol    TEXT NOT NULL,
    metric    TEXT NOT NULL,
    op        TEXT NOT NULL,
    threshold REAL NOT NULL,
    active    INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE watches (
    id           TEXT PRIMARY KEY,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    user         TEXT NOT NULL DEFAULT 'default',
    symbol       TEXT NOT NULL,
    metric       TEXT NOT NULL,
    op           TEXT NOT NULL,
    threshold    REAL NOT NULL,
    window       TEXT,
    channel      TEXT NOT NULL DEFAULT 'telegram:default',
    cooldown_sec INTEGER NOT NULL DEFAULT 3600,
    last_fired_at TEXT,
    disabled     INTEGER NOT NULL DEFAULT 0,
    note         TEXT
);
CREATE TABLE backtest_jobs (
    id            TEXT PRIMARY KEY,
    strategy      TEXT NOT NULL,
    params_json   TEXT NOT NULL DEFAULT '{}',
    universe_json TEXT NOT NULL DEFAULT '[]',
    start_date    TEXT NOT NULL,
    end_date      TEXT NOT NULL,
    market        TEXT NOT NULL DEFAULT 'ID',
    status        TEXT NOT NULL,
    result_json   TEXT,
    error         TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at  TEXT
);
"""


@pytest.fixture
def old_db(monkeypatch, tmp_path):
    """A populated v0.3.0-shaped database, wired up as FINANCE_DB."""
    path = tmp_path / "old.db"
    monkeypatch.setenv("FINANCE_DB", str(path))
    conn = sqlite3.connect(path, isolation_level=None)
    conn.executescript(OLD_SCHEMA)
    conn.execute("INSERT INTO accounts (id, name) VALUES (1, 'Main')")
    conn.execute(
        "INSERT INTO transactions (account_id, symbol, side, quantity, price,"
        " executed_at) VALUES (1, 'BBCA', 'BUY', 100, 9000, '2026-01-02')"
    )
    conn.execute("INSERT INTO watchlists (id, name) VALUES (1, 'Core')")
    conn.execute(
        "INSERT INTO alerts (symbol, metric, op, threshold) "
        "VALUES ('BBRI', 'price', '>', 5000)"
    )
    conn.execute(
        "INSERT INTO watches (id, user, symbol, metric, op, threshold) "
        "VALUES ('w_1', 'default', 'TLKM', 'price', '<', 3000)"
    )
    conn.execute(
        "INSERT INTO backtest_jobs (id, strategy, start_date, end_date, status)"
        " VALUES ('bt_1', 'sma_cross', '2026-01-01', '2026-06-01', 'done')"
    )
    conn.close()
    return path


def _columns(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def test_migrates_old_database_without_losing_rows(old_db):
    assert migrations.migrate() == [1, 2, 3]
    with connect() as conn:
        for table, expected in [
            ("accounts", 1), ("transactions", 1), ("watchlists", 1),
            ("alerts", 1), ("watches", 1), ("backtest_jobs", 1),
        ]:
            got = conn.execute(f"SELECT count(*) c FROM {table}").fetchone()["c"]
            assert got == expected, f"{table} lost rows"


def test_root_tables_gain_tenant_id_backfilled_to_local(old_db):
    migrations.migrate()
    with connect() as conn:
        for table in ("accounts", "watchlists", "alerts", "watches",
                      "backtest_jobs"):
            assert "tenant_id" in _columns(conn, table), table
            rows = conn.execute(f"SELECT tenant_id FROM {table}").fetchall()
            assert [r["tenant_id"] for r in rows] == ["local"], table


def test_child_tables_are_left_alone(old_db):
    """They inherit their tenant through the foreign key to a root row."""
    migrations.migrate()
    with connect() as conn:
        assert "tenant_id" not in _columns(conn, "transactions")


def test_watches_user_column_is_renamed_not_duplicated(old_db):
    migrations.migrate()
    with connect() as conn:
        cols = _columns(conn, "watches")
    assert "tenant_id" in cols
    assert "user" not in cols, "old column left behind — two names, one meaning"


def test_foreign_keys_survive_the_table_rebuild(old_db):
    """accounts is rebuilt for the UNIQUE change; transactions points at it."""
    migrations.migrate()
    with connect() as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        row = conn.execute(
            "SELECT t.symbol FROM transactions t JOIN accounts a"
            " ON a.id = t.account_id"
        ).fetchone()
    assert row["symbol"] == "BBCA"


def test_account_names_are_unique_per_tenant_not_globally(old_db):
    migrations.migrate()
    with connect() as conn:
        # Same name under a different tenant is now allowed...
        conn.execute(
            "INSERT INTO accounts (tenant_id, name) VALUES ('tg_42', 'Main')"
        )
        # ...but still rejected within one tenant.
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO accounts (tenant_id, name) VALUES ('local', 'Main')"
            )


def test_migrate_is_idempotent(old_db):
    assert migrations.migrate() == [1, 2, 3]
    assert migrations.migrate() == []


def test_migrate_on_a_fresh_current_schema_is_a_noop(monkeypatch, tmp_path):
    """A database built from today's schema.sql needs no data changes."""
    monkeypatch.setenv("FINANCE_DB", str(tmp_path / "fresh.db"))
    from finance_mcp.backtest import db as btdb
    from finance_mcp.news import db as ndb
    from finance_mcp.portfolio import db as pdb
    from finance_mcp.watch import db as wdb
    pdb.init(); wdb.init(); ndb.init(); btdb.init()

    migrations.migrate()
    with connect() as conn:
        assert "tenant_id" in _columns(conn, "accounts")
        assert conn.execute("SELECT count(*) c FROM accounts").fetchone()["c"] == 0


def test_news_tables_stay_shared(monkeypatch, tmp_path):
    """Articles are a common corpus, not per-tenant state."""
    monkeypatch.setenv("FINANCE_DB", str(tmp_path / "news.db"))
    from finance_mcp.news import db as ndb
    from finance_mcp.portfolio import db as pdb
    pdb.init(); ndb.init()
    migrations.migrate()
    with connect() as conn:
        for table in ("articles", "article_symbols", "article_sentiment"):
            assert "tenant_id" not in _columns(conn, table), table


def _bootstrap_all() -> None:
    """The order server.py uses: every schema.sql, then migrations."""
    from finance_mcp.backtest import db as btdb
    from finance_mcp.news import db as ndb
    from finance_mcp.portfolio import db as pdb
    from finance_mcp.watch import db as wdb
    pdb.init(); wdb.init(); ndb.init(); btdb.init()
    migrations.migrate()


def test_real_upgrade_path_runs_schema_bootstrap_before_migrating(old_db):
    """schema.sql must survive being re-run against a pre-tenant database.

    This is the path a real install takes and the one the other tests missed:
    they called migrate() on the old database directly, never init() first.
    An index declared in schema.sql over a column that only migrations add
    raises "no such column: tenant_id" here, long before migrate() is reached.
    """
    _bootstrap_all()
    with connect() as conn:
        assert "tenant_id" in _columns(conn, "accounts")
        assert conn.execute(
            "SELECT count(*) c FROM accounts"
        ).fetchone()["c"] == 1


def test_tenant_indexes_exist_on_both_paths(old_db, monkeypatch, tmp_path):
    """Fresh and upgraded databases converge on the same indexes."""
    def index_names() -> set[str]:
        with connect() as conn:
            return {r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'")}

    _bootstrap_all()
    upgraded = index_names()

    monkeypatch.setenv("FINANCE_DB", str(tmp_path / "fresh2.db"))
    _bootstrap_all()
    fresh = index_names()

    tenant_indexes = {"idx_accounts_tenant", "idx_watchlists_tenant",
                      "idx_alerts_tenant", "idx_watches_tenant",
                      "idx_backtest_jobs_tenant"}
    assert tenant_indexes <= upgraded
    assert tenant_indexes <= fresh
