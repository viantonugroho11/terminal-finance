# ADR-0028: News + sentiment layer

- Status: Proposed
- Date: 2026-08-14
- Deciders: Finance Terminal team

## Context

Fundamentals + price answer "what". News answers "why". No source of narrative in terminal today. Users leave to read Kontan / Bisnis Indonesia / IDNFinancials / CNBC / Reuters.

Existing providers publish RSS or scrapable feeds. Sentiment scoring needed to fold hundreds of articles into one signal per symbol.

## Decision

New `news-mcp` capability inside existing finance-mcp (not sidecar).

1. Ingest: pull configured RSS list every 15min. Sources v1: Kontan, Bisnis, IDNFinancials, Reuters biz, CNBC markets, IDX press releases.
2. Store: `news.duckdb` — `(id, url, title, source, published_at, symbols[], body, sentiment, sentiment_confidence)`.
3. Symbol tagger: regex on ticker patterns + company-name allowlist per symbol (built from `idx_tickers.txt` + US S&P 500).
4. Sentiment: DeepSeek zero-shot classifier — `{positive, neutral, negative}` + one-sentence rationale. Cached by article id.
5. Tools: `get_news(symbol?, since?, limit)`, `news_sentiment(symbol, window)` returning `{score: -1..1, count, top_articles}`.
6. Skill `news-brief` composes latest + sentiment + link back.

## Consequences

- Positive: closes narrative gap. Enables event-study on sentiment vs price.
- Positive: bilingual — Indonesian + English sources side by side.
- Negative: RSS coverage misses paywalled scoops. Accepted for v1.
- Negative: LLM sentiment cost per article — throttle to headline + first paragraph; cache aggressively.
- Negative: legal — RSS is meant for aggregation; storing full body may exceed fair use per source. Store snippet + link, fetch full body on demand only.
- Follow-ups: source-quality weighting, per-source dedup (same wire repeated), alert integration (sentiment spike → watch rule fires).

## Alternatives considered

- **Third-party (NewsAPI, Benzinga).** Rejected: paid, weak Indonesian coverage.
- **Vector search over articles.** Deferred: keyword + symbol tag covers 90% of queries; vector adds cost without proportional gain until archive >100k articles.
- **Local sentiment model (FinBERT).** Rejected v1: English-only; Indonesian coverage weak. Revisit if DeepSeek cost becomes issue.

## References

- ADR-0011 (provenance).
- ADR-0023 (alert engine) — consumer of sentiment spike signal.
