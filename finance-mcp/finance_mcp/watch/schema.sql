-- Watch engine schema — ADR-0023.

CREATE TABLE IF NOT EXISTS watches (
    id             TEXT PRIMARY KEY,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    user           TEXT NOT NULL DEFAULT 'default',
    symbol         TEXT NOT NULL,
    metric         TEXT NOT NULL,
    op             TEXT NOT NULL CHECK (op IN ('>','<','>=','<=','==')),
    threshold      REAL NOT NULL,
    window         TEXT,
    channel        TEXT NOT NULL DEFAULT 'telegram:default',
    cooldown_sec   INTEGER NOT NULL DEFAULT 3600,
    last_fired_at  TEXT,
    disabled       INTEGER NOT NULL DEFAULT 0,
    note           TEXT
);

CREATE INDEX IF NOT EXISTS idx_watches_symbol ON watches(symbol);
CREATE INDEX IF NOT EXISTS idx_watches_active ON watches(disabled, last_fired_at);

CREATE TABLE IF NOT EXISTS watch_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id    TEXT NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
    fired_at    TEXT NOT NULL DEFAULT (datetime('now')),
    metric_value REAL NOT NULL,
    delivered   INTEGER NOT NULL DEFAULT 0,
    error       TEXT
);

CREATE INDEX IF NOT EXISTS idx_watch_events_time ON watch_events(fired_at);
