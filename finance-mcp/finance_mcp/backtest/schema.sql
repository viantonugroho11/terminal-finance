-- Backtest job store — ADR-0029.

CREATE TABLE IF NOT EXISTS backtest_jobs (
    id            TEXT PRIMARY KEY,       -- bt_<hex>
    strategy      TEXT NOT NULL,
    params_json   TEXT NOT NULL DEFAULT '{}',
    universe_json TEXT NOT NULL DEFAULT '[]',
    start_date    TEXT NOT NULL,
    end_date      TEXT NOT NULL,
    market        TEXT NOT NULL DEFAULT 'ID',   -- ID | US | CRYPTO
    status        TEXT NOT NULL CHECK (status IN ('queued','running','done','error')),
    result_json   TEXT,
    error         TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_bt_jobs_status ON backtest_jobs(status);
CREATE INDEX IF NOT EXISTS idx_bt_jobs_created ON backtest_jobs(created_at DESC);
