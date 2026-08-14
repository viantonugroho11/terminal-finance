-- News + sentiment schema — ADR-0028.
-- Uses shared finance.db (spec suggests DuckDB; SQLite chosen to avoid
-- new dep and match portfolio/watch pattern).

CREATE TABLE IF NOT EXISTS articles (
    id            TEXT PRIMARY KEY,   -- sha256(url)[:16]
    url           TEXT NOT NULL UNIQUE,
    title         TEXT NOT NULL,
    source        TEXT NOT NULL,
    published_at  TEXT NOT NULL,
    snippet       TEXT,
    lang          TEXT NOT NULL DEFAULT 'id',
    fetched_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_articles_pub  ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_src  ON articles(source);

CREATE TABLE IF NOT EXISTS article_symbols (
    article_id  TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    symbol      TEXT NOT NULL,
    PRIMARY KEY (article_id, symbol)
);

CREATE INDEX IF NOT EXISTS idx_article_symbols_sym ON article_symbols(symbol);

CREATE TABLE IF NOT EXISTS article_sentiment (
    article_id   TEXT PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
    label        TEXT NOT NULL CHECK (label IN ('positive','neutral','negative')),
    confidence   REAL NOT NULL,
    rationale    TEXT,
    scored_at    TEXT NOT NULL DEFAULT (datetime('now')),
    model        TEXT NOT NULL DEFAULT 'deepseek-chat'
);
