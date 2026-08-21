-- Portfolio schema. Structured state; do not put this in Hermes memory.

CREATE TABLE IF NOT EXISTS accounts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Owner. Single-user installs never leave 'local'; see migrations.py.
    tenant_id    TEXT NOT NULL DEFAULT 'local',
    name         TEXT NOT NULL,
    currency     TEXT NOT NULL DEFAULT 'USD',
    kind         TEXT NOT NULL DEFAULT 'brokerage', -- brokerage | crypto | retirement | cash
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (tenant_id, name)
);


CREATE TABLE IF NOT EXISTS transactions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id   INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    symbol       TEXT NOT NULL,
    side         TEXT NOT NULL CHECK (side IN ('BUY','SELL','DIV','FEE','DEPOSIT','WITHDRAW')),
    quantity     REAL NOT NULL,
    price        REAL NOT NULL,     -- unit price; for DEPOSIT/WITHDRAW use 1.0 and put amount in quantity
    fee          REAL NOT NULL DEFAULT 0,
    currency     TEXT NOT NULL DEFAULT 'USD',
    executed_at  TEXT NOT NULL,     -- ISO8601
    note         TEXT
);

CREATE INDEX IF NOT EXISTS idx_tx_account_symbol ON transactions(account_id, symbol);
CREATE INDEX IF NOT EXISTS idx_tx_executed_at    ON transactions(executed_at);

CREATE TABLE IF NOT EXISTS watchlists (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id    TEXT NOT NULL DEFAULT 'local',
    name         TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (tenant_id, name)
);


CREATE TABLE IF NOT EXISTS watchlist_items (
    watchlist_id INTEGER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    symbol       TEXT NOT NULL,
    added_at     TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (watchlist_id, symbol)
);

CREATE TABLE IF NOT EXISTS alerts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id    TEXT NOT NULL DEFAULT 'local',
    symbol       TEXT NOT NULL,
    metric       TEXT NOT NULL,     -- price | rsi | change_pct | drawdown
    op           TEXT NOT NULL CHECK (op IN ('>','<','>=','<=','==')),
    threshold    REAL NOT NULL,
    active       INTEGER NOT NULL DEFAULT 1,
    last_fired_at TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

