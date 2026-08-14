# Spec: News + sentiment layer

Ref: ADR-0028.

## Goal

`news BBCA` returns recent tagged articles + one-line sentiment; `news_sentiment BBCA window=7d` returns aggregate score.

## Success conditions

- `pytest finance-mcp/tests/test_news.py` green: RSS parse, symbol tag, sentiment cache.
- ≥5 sources ingested every 15min; symbol-tag precision >90% on hand-labeled 100-article sample.
- Sentiment call cached per article — never re-called.

## Deliverables

### 1. Ingest

Path: `finance-mcp/finance_mcp/ingest/news.py`.

Cron: `*/15 * * * *`.

Sources v1: Kontan, Bisnis, IDNFinancials, Reuters biz, CNBC markets, IDX press.

Steps per source:
1. Fetch RSS.
2. Dedup by URL SHA.
3. Insert `articles(id, url, title, source, published_at, snippet)` in `news.duckdb`.
4. Tag symbols (regex + name allowlist) → `article_symbols(article_id, symbol)`.
5. Enqueue sentiment task.

### 2. Symbol tagger

Path: `finance-mcp/finance_mcp/news/tagger.py`.

Load per-symbol aliases: `BBCA` matches `["BBCA", "Bank Central Asia", "BCA"]`. Generate from `idx_tickers.txt` + `sp500.txt`. Manual override in `data/symbol_aliases.yaml`.

### 3. Sentiment worker

Path: `finance-mcp/finance_mcp/news/sentiment.py`.

Input: title + first paragraph (cap 300 tokens). DeepSeek zero-shot: `{label: pos|neu|neg, confidence: 0..1, rationale: str}`. Cache by article id in `article_sentiment` table.

### 4. MCP tools

- `get_news(symbol=None, since=None, limit=20) -> list[Article]`
- `news_sentiment(symbol, window="7d") -> {score: -1..1, count, positive_pct, negative_pct, top_articles: [Article]}`

Score = `mean(±1 * confidence)` where pos=+1, neg=-1, neu=0.

### 5. Skill `news-brief`

Path: `finance-skills/news-brief/SKILL.md`.

Returns: latest 5 with sentiment tag, aggregate score, top headline of week.

### 6. Alert integration

New watch metric `sentiment_spike:<symbol>` — fires when 24h avg > +0.5 or < -0.5 with ≥5 articles. Reuses ADR-0023 evaluator.

## Out of scope

- Paywalled sources.
- Vector search (deferred).
- Local sentiment model.

## Milestones

1. Ingest + dedup + duckdb schema (1d).
2. Tagger + aliases + precision test (1d).
3. Sentiment worker + cache + rate limit (0.5d).
4. Tools + provenance (0.5d).
5. `news-brief` skill (0.5d).
6. Alert metric wiring (0.5d).

Total: ~4d.
