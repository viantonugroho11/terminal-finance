-- Lot-tracking schema (ADR-0027). Lives alongside the running-avg
-- `transactions` table — the two are independent stores; migration
-- one-shot copies transactions → synthetic buy lots.

CREATE TABLE IF NOT EXISTS lots (
    id            TEXT PRIMARY KEY,      -- l_<hex>
    account       TEXT NOT NULL DEFAULT 'main',
    symbol        TEXT NOT NULL,
    qty           REAL NOT NULL,         -- original buy qty; sells reduce via closes table
    qty_remaining REAL NOT NULL,         -- qty minus closed portions
    price         REAL NOT NULL,         -- unit price at buy (excludes fee)
    currency      TEXT NOT NULL DEFAULT 'IDR',
    fee           REAL NOT NULL DEFAULT 0,
    tax           REAL NOT NULL DEFAULT 0,
    acquired_at   TEXT NOT NULL,         -- ISO8601 UTC
    note          TEXT
);

CREATE INDEX IF NOT EXISTS idx_lots_symbol   ON lots(symbol);
CREATE INDEX IF NOT EXISTS idx_lots_open     ON lots(qty_remaining) WHERE qty_remaining > 0;

CREATE TABLE IF NOT EXISTS lot_closes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id       TEXT NOT NULL REFERENCES lots(id) ON DELETE CASCADE,
    qty          REAL NOT NULL,
    price        REAL NOT NULL,          -- unit sell price
    currency     TEXT NOT NULL DEFAULT 'IDR',
    fee          REAL NOT NULL DEFAULT 0,
    tax          REAL NOT NULL DEFAULT 0,
    closed_at    TEXT NOT NULL,
    note         TEXT
);

CREATE INDEX IF NOT EXISTS idx_lot_closes_lot ON lot_closes(lot_id);
