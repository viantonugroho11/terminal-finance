-- Daily broker-activity snapshots — closes the ADR-0026 multi-day gap.
--
-- The IDX broker-summary endpoint exposes no historical-date parameter: it
-- answers for the latest session only. broker_flow_agg() therefore could not
-- aggregate over N days no matter how it was written. Accumulating a snapshot
-- per trading day locally is the way to get the history the tool promises.
--
-- Keyed by (symbol, date, broker_code) so re-running a snapshot on the same
-- day overwrites rather than double-counts.

CREATE TABLE IF NOT EXISTS broker_daily (
    symbol      TEXT NOT NULL,
    date        TEXT NOT NULL,          -- trading date, from the provider payload
    broker_code TEXT NOT NULL,
    broker_name TEXT,
    buy_value   REAL NOT NULL DEFAULT 0,
    sell_value  REAL NOT NULL DEFAULT 0,
    net_value   REAL NOT NULL DEFAULT 0,
    captured_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, date, broker_code)
);

CREATE INDEX IF NOT EXISTS idx_broker_daily_sym_date
    ON broker_daily(symbol, date DESC);
