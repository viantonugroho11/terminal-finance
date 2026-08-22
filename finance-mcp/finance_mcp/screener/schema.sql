-- Screener snapshot — ADR-0025.
--
-- Spec proposed DuckDB; SQLite on the shared finance.db is used instead, for
-- the same reason ADR-0028 gave: no new dependency, and it matches the
-- portfolio / watch / news / flow pattern.
--
-- One row per (symbol, snapshot_date). Re-running a snapshot the same day
-- replaces rather than appends.

CREATE TABLE IF NOT EXISTS screener_snapshot (
    symbol                    TEXT NOT NULL,
    snapshot_date             TEXT NOT NULL,
    market                    TEXT,
    name                      TEXT,
    sector                    TEXT,
    industry                  TEXT,
    currency                  TEXT,
    price                     REAL,
    market_cap                REAL,
    pe_ratio                  REAL,
    forward_pe                REAL,
    peg_ratio                 REAL,
    price_to_book             REAL,
    price_to_sales            REAL,
    profit_margin             REAL,
    operating_margin          REAL,
    return_on_equity          REAL,
    return_on_assets          REAL,
    revenue_growth            REAL,
    earnings_growth           REAL,
    debt_to_equity            REAL,
    current_ratio             REAL,
    free_cashflow             REAL,
    dividend_yield            REAL,
    beta                      REAL,
    net_interest_margin       REAL,
    non_performing_loan_ratio REAL,
    capital_adequacy_ratio    REAL,
    loan_to_deposit_ratio     REAL,
    casa_ratio                REAL,
    loan_growth               REAL,
    deposit_growth            REAL,
    captured_at               TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_screener_date   ON screener_snapshot(snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_screener_market ON screener_snapshot(market, snapshot_date DESC);
