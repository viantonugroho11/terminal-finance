"""News + sentiment — ADR-0028 unit tests. No network."""
from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault(
    "FINANCE_DB",
    tempfile.NamedTemporaryFile(suffix=".db", delete=False).name,
)

from finance_mcp.news import db as ndb  # noqa: E402
from finance_mcp.news import ingest, sentiment, store, tagger
from finance_mcp.news.sources import Source  # noqa: E402
from finance_mcp.portfolio import db as pdb  # noqa: E402

pdb.init()
ndb.init()


def _ago(hours: float) -> str:
    """Timestamp `hours` before now, ISO-8601 UTC.

    Store queries filter on a window measured from `datetime.now()`, so
    fixtures must be clock-relative. Hardcoded dates silently expire: the
    stamps here were pinned to 2026-08-14, and once wall-clock passed
    2026-08-21 the 168h-window test started failing and the 24h-window test
    began passing for the wrong reason (empty window, not the <5 threshold).
    """
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _reset() -> None:
    from finance_mcp.portfolio.db import connect
    with connect() as conn:
        conn.execute("DELETE FROM article_sentiment")
        conn.execute("DELETE FROM article_symbols")
        conn.execute("DELETE FROM articles")


# ── tagger ─────────────────────────────────────────────────────────────

def test_tagger_finds_alias_and_ticker() -> None:
    tagger.clear_cache()
    hits = tagger.tag("Bank Central Asia BBCA membukukan laba naik 12%")
    assert "BBCA" in hits


def test_tagger_no_false_positive_on_substring() -> None:
    tagger.clear_cache()
    # "APPLES" should not match AAPL alias "Apple" without word boundary
    hits = tagger.tag("Pineapples are healthy")
    assert "AAPL" not in hits


# ── store ──────────────────────────────────────────────────────────────

def test_insert_and_dedup() -> None:
    _reset()
    url = "https://example.com/a"
    aid1 = store.insert_article(
        url=url, title="Test A", source="kontan",
        published_at=_ago(1),
    )
    aid2 = store.insert_article(
        url=url, title="Test A dup", source="kontan",
        published_at=_ago(1),
    )
    assert aid1 == aid2
    # only one row inserted (INSERT OR IGNORE)
    got = store.list_news(limit=50)
    assert len([g for g in got if g["url"] == url]) == 1


def test_list_news_by_symbol() -> None:
    _reset()
    aid = store.insert_article(
        url="https://example.com/b", title="BBCA laba naik",
        source="kontan", published_at=_ago(1),
    )
    store.tag_article(aid, ["BBCA"])
    rows = store.list_news(symbol="BBCA")
    assert len(rows) == 1
    assert rows[0]["id"] == aid


def test_sentiment_score_requires_min_articles() -> None:
    _reset()
    for i in range(4):
        aid = store.insert_article(
            url=f"https://example.com/c{i}",
            title=f"BBCA berita {i}",
            source="kontan",
            published_at=_ago(2),
        )
        store.tag_article(aid, ["BBCA"])
        store.set_sentiment(aid, "positive", 0.8, "test")
    # 4 articles, all inside the window — None must come from the <5
    # threshold, not from an empty window.
    assert store.sentiment_summary("BBCA", window_hours=24)["count"] == 4
    assert store.sentiment_score("BBCA", window_hours=24) is None


def test_sentiment_summary_shape() -> None:
    _reset()
    for i in range(6):
        aid = store.insert_article(
            url=f"https://example.com/d{i}",
            title=f"BBCA news {i}",
            source="kontan",
            published_at=_ago(3),
        )
        store.tag_article(aid, ["BBCA"])
        label = "positive" if i % 2 == 0 else "negative"
        store.set_sentiment(aid, label, 0.9, "test")
    summary = store.sentiment_summary("BBCA", window_hours=168)
    assert summary["count"] == 6
    assert summary["positive_pct"] == pytest.approx(50.0)
    assert summary["negative_pct"] == pytest.approx(50.0)
    assert summary["score"] == pytest.approx(0.0, abs=0.001)
    assert len(summary["top_articles"]) == 5


# ── sentiment classifiers ──────────────────────────────────────────────

def test_lexicon_classify_positive() -> None:
    out = sentiment.lexicon_classify("Company reports record profit and surge in growth")
    assert out["label"] == "positive"
    assert out["confidence"] > 0.5


def test_lexicon_classify_negative() -> None:
    out = sentiment.lexicon_classify("Saham anjlok, rugi besar dan risiko meningkat")
    assert out["label"] == "negative"


def test_lexicon_classify_neutral_when_no_terms() -> None:
    out = sentiment.lexicon_classify("The meeting was held on Tuesday")
    assert out["label"] == "neutral"


def test_score_missing_uses_injected_classifier() -> None:
    _reset()
    for i in range(3):
        store.insert_article(
            url=f"https://example.com/e{i}",
            title=f"BBCA news {i}", source="kontan",
            published_at=_ago(4),
        )
    calls = []

    def fake(text: str) -> dict:
        calls.append(text)
        return {"label": "positive", "confidence": 0.7, "rationale": "test"}

    n = asyncio.run(sentiment.score_missing(classifier=fake, limit=10))
    assert n == 3
    assert len(calls) == 3
    # second run should score 0 (all scored)
    assert asyncio.run(sentiment.score_missing(classifier=fake, limit=10)) == 0


# ── ingest ─────────────────────────────────────────────────────────────

_SAMPLE_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>Kontan</title>
<item>
  <title>BBCA membukukan laba naik 12% year-on-year</title>
  <link>https://example.com/ing1</link>
  <description>Bank Central Asia reports strong quarterly results</description>
  <pubDate>Thu, 14 Aug 2026 05:00:00 +0000</pubDate>
</item>
<item>
  <title>Astra International kinerja Q2</title>
  <link>https://example.com/ing2</link>
  <description>Astra reports profit growth</description>
  <pubDate>Thu, 14 Aug 2026 05:30:00 +0000</pubDate>
</item>
</channel></rss>
"""


def test_ingest_parses_and_tags() -> None:
    _reset()
    tagger.clear_cache()
    src = Source("test", "https://example.com/rss", "id")

    async def fetcher(_s: Source) -> str:
        return _SAMPLE_RSS

    report = asyncio.run(ingest.ingest_source(src, fetcher=fetcher))
    assert report.error is None
    assert report.fetched == 2
    assert report.new == 2
    assert report.tagged >= 1

    bbca = store.list_news(symbol="BBCA")
    assert len(bbca) == 1
    assert "BBCA" in bbca[0]["title"]


def test_ingest_dedup_on_second_run() -> None:
    _reset()
    src = Source("test", "https://example.com/rss", "id")

    async def fetcher(_s: Source) -> str:
        return _SAMPLE_RSS

    asyncio.run(ingest.ingest_source(src, fetcher=fetcher))
    r2 = asyncio.run(ingest.ingest_source(src, fetcher=fetcher))
    assert r2.new == 0
