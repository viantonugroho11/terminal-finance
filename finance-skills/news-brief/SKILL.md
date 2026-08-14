---
name: news-brief
description: Recent news + sentiment for a symbol or the market. Use when user says "berita", "news", "kabar", "sentimen".
version: 0.1.0
author: Finance Hermes
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, News, Sentiment]
    related_skills: [stock-analysis, market-overview, watch]
    requires_tools:
      - finance.get_news
      - finance.news_sentiment
      - finance.news_ingest_once
---

# News Brief

Answer news/sentiment questions grounded ONLY in ingested articles.
Never fabricate headlines, sources, dates, or sentiment labels.

## When to Use

- "berita BBCA", "news NVDA", "kabar terbaru TLKM"
- "sentimen BBRI minggu ini", "sentiment BTC"
- "apa kata pasar soal ...?"

## Flow

1. Resolve symbol (upper-case ticker).
2. Call `finance.get_news(symbol=..., limit=5)` — returns latest tagged
   articles with per-article sentiment.
3. Call `finance.news_sentiment(symbol=..., window_hours=168)` for
   aggregate score.
4. Compose reply: aggregate line + bulleted top 3 headlines with
   `[label · conf]` tags and links.

## Rules

- If `count == 0`, say "no articles ingested for this symbol in window"
  — do NOT synthesize.
- Do NOT translate headlines; keep original language, tag `lang`.
- If aggregate `score` is null (<5 articles), do not report a score.
- Always show `retrieved_at` from provenance.
