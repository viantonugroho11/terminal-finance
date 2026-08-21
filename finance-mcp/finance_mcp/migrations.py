"""Schema migrations for the shared finance.db.

Until now the four packages (portfolio, watch, news, backtest) each ran
`CREATE TABLE IF NOT EXISTS` from their own schema.sql. That bootstraps a
fresh database but cannot change an existing one — adding a column or
altering a constraint on a live DB had no path at all.

Design notes:

* **Idempotent, not just versioned.** Every migration checks the state it
  intends to create before acting, so a fresh DB (already built in the new
  shape by schema.sql) and an old DB converge on the same result. The
  version table records what ran; the guards make a re-run harmless.
* **Ordered and recorded.** `schema_migrations` holds applied versions so a
  large rebuild is not attempted twice.
* Run after the schema.sql bootstrap, never before.
"""
from __future__ import annotations

import sqlite3
from typing import Callable

from .portfolio.db import connect

# Tenant every pre-existing row belongs to. Single-user installs stay on this
# value forever and never see the column.
DEFAULT_TENANT = "local"


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _ensure_tenant(conn: sqlite3.Connection, table: str) -> None:
    """Give `table` a tenant_id and its index.

    Both halves are conditional and independent: a fresh database already has
    the column from schema.sql but never the index, because schema.sql has to
    stay runnable against an old database where the column does not exist yet.
    """
    if not _table_exists(conn, table):
        return
    if "tenant_id" not in _columns(conn, table):
        conn.execute(
            f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT NOT NULL "
            f"DEFAULT '{DEFAULT_TENANT}'"
        )
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_tenant ON {table}(tenant_id)")


def _m001_tenant_columns(conn: sqlite3.Connection) -> None:
    """Add tenant_id to the root tables.

    Child tables (transactions, watchlist_items, watch_events) inherit their
    tenant through the foreign key to a root row, so they stay untouched.

    The news tables are deliberately excluded: articles, their symbol tags and
    their sentiment scores are a shared corpus that every tenant reads. That is
    the "shared read pool" ADR-0030 planned to build out of symlinks; on a
    single database it costs nothing.
    """
    for table in ("accounts", "watchlists", "alerts", "backtest_jobs"):
        _ensure_tenant(conn, table)


def _m002_watches_user_to_tenant(conn: sqlite3.Connection) -> None:
    """Rename watches.user to tenant_id.

    `user` was already a tenant key in embryo — store.list_all() filtered on
    it with a 'default' fallback. Adding tenant_id beside it would leave two
    columns meaning the same thing, so rename instead and carry the old values
    across ('default' becomes the local tenant).
    """
    if not _table_exists(conn, "watches"):
        return
    cols = _columns(conn, "watches")
    if "tenant_id" in cols or "user" not in cols:
        _ensure_tenant(conn, "watches")         # fresh DB, or already renamed
        return
    conn.execute("ALTER TABLE watches RENAME COLUMN user TO tenant_id")
    conn.execute(
        "UPDATE watches SET tenant_id = ? WHERE tenant_id = 'default'",
        (DEFAULT_TENANT,),
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_watches_tenant ON watches(tenant_id)")


def _rebuild_unique_per_tenant(conn: sqlite3.Connection, table: str, ddl: str) -> None:
    """Replace `table` with `ddl`, preserving rows and ids.

    SQLite cannot alter a constraint in place, so a UNIQUE(name) that has to
    become UNIQUE(tenant_id, name) needs the documented 12-step rebuild. Ids
    are copied verbatim, so foreign keys pointing at this table stay valid.
    """
    # Individual execute() calls, never executescript(): the latter commits
    # any open transaction before it runs, which would silently break the
    # atomicity the caller set up with BEGIN.
    cols = ", ".join(sorted(_columns(conn, table)))
    conn.execute(f"CREATE TABLE {table}__new ({ddl})")
    conn.execute(f"INSERT INTO {table}__new ({cols}) SELECT {cols} FROM {table}")
    conn.execute(f"DROP TABLE {table}")
    conn.execute(f"ALTER TABLE {table}__new RENAME TO {table}")


def _m003_unique_per_tenant(conn: sqlite3.Connection) -> None:
    """Scope the UNIQUE name constraints to the tenant.

    accounts.name and watchlists.name were globally unique. Under more than
    one tenant that is wrong: two people cannot both own an account called
    "Main". Cheap to fix while the database holds a single tenant's rows;
    expensive once it does not.
    """
    specs = {
        "accounts": """
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id  TEXT NOT NULL DEFAULT 'local',
            name       TEXT NOT NULL,
            currency   TEXT NOT NULL DEFAULT 'USD',
            kind       TEXT NOT NULL DEFAULT 'brokerage',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (tenant_id, name)
        """,
        "watchlists": """
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id  TEXT NOT NULL DEFAULT 'local',
            name       TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (tenant_id, name)
        """,
    }
    for table, ddl in specs.items():
        if not _table_exists(conn, table):
            continue
        # Already scoped? sqlite_master holds the CREATE statement verbatim.
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()["sql"]
        if "UNIQUE (tenant_id, name)" in sql.replace("UNIQUE(tenant_id, name)",
                                                     "UNIQUE (tenant_id, name)"):
            continue
        _rebuild_unique_per_tenant(conn, table, ddl)
        _ensure_tenant(conn, table)             # the rebuild drops the index


MIGRATIONS: list[tuple[int, str, Callable[[sqlite3.Connection], None]]] = [
    (1, "tenant_id on root tables", _m001_tenant_columns),
    (2, "watches.user renamed to tenant_id", _m002_watches_user_to_tenant),
    (3, "UNIQUE(name) scoped to tenant", _m003_unique_per_tenant),
]


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY,"
        " name TEXT NOT NULL,"
        " applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    return {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}


def migrate() -> list[int]:
    """Apply pending migrations. Returns the versions applied this call."""
    ran: list[int] = []
    conn = connect()
    try:
        done = applied_versions(conn)
        for version, name, fn in MIGRATIONS:
            if version in done:
                continue
            # Table rebuilds must not run with foreign keys enforced; the
            # connection turns them on, so drop the guard for the transaction
            # and check integrity before committing.
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("BEGIN")
            try:
                fn(conn)
                violations = conn.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise sqlite3.IntegrityError(
                        f"migration {version} ({name}) left "
                        f"{len(violations)} foreign-key violation(s)"
                    )
                conn.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                    (version, name),
                )
                conn.execute("COMMIT")
                ran.append(version)
            except Exception:
                # Roll back only if the transaction is still open; a statement
                # that commits implicitly would make ROLLBACK itself raise and
                # mask the real failure.
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.execute("PRAGMA foreign_keys = ON")
    finally:
        conn.close()
    return ran
