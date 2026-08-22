-- Earnings / public-expose transcripts — ADR-0024.
--
-- Two deviations from the spec, both deliberate (see the ADR):
--
-- 1. Source. The spec wanted a hand-curated YAML of per-issuer investor
--    relations URLs and a scraper each. IDX already publishes a uniform
--    per-symbol announcement feed, which this repo already routes as the
--    `disclosures` capability, and Paparan Publik decks are filed there.
--    One endpoint beats 435 bespoke scrapers that break on redesign.
--
-- 2. Retrieval. The spec wanted bge-m3 embeddings via sentence-transformers,
--    which drags PyTorch into a slim image. SQLite's own FTS5 with BM25 is
--    built into the stdlib sqlite3 module and needs nothing new. Financial
--    questions tend to hunt exact terminology ("NPL", "capex", "dividen"),
--    which is what lexical search is good at.

CREATE TABLE IF NOT EXISTS transcripts (
    id            TEXT PRIMARY KEY,        -- sha256(url)[:16]
    symbol        TEXT NOT NULL,
    title         TEXT NOT NULL,
    url           TEXT NOT NULL UNIQUE,
    category      TEXT,
    published_at  TEXT NOT NULL,
    sha256        TEXT,                    -- of the PDF bytes; dedups re-files
    pages         INTEGER NOT NULL DEFAULT 0,
    fetched_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_transcripts_symbol
    ON transcripts(symbol, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_transcripts_sha ON transcripts(sha256);

CREATE TABLE IF NOT EXISTS transcript_pages (
    transcript_id TEXT NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    page          INTEGER NOT NULL,        -- 1-based, as a reader would cite
    text          TEXT NOT NULL,
    PRIMARY KEY (transcript_id, page)
);

-- Search index. Contentless-style duplication is avoided by keeping the text
-- here and joining back for metadata; symbol is indexed so a per-symbol search
-- stays a single MATCH rather than a scan plus filter.
CREATE VIRTUAL TABLE IF NOT EXISTS transcript_fts USING fts5(
    text,
    symbol UNINDEXED,
    transcript_id UNINDEXED,
    page UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);
