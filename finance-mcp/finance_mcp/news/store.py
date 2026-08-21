"""News store — CRUD + aggregate queries."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from ..portfolio.db import connect


def article_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def insert_article(*, url: str, title: str, source: str,
                   published_at: str, snippet: str | None = None,
                   lang: str = "id") -> str:
    aid = article_id(url)
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO articles"
            "(id, url, title, source, published_at, snippet, lang) "
            "VALUES (?,?,?,?,?,?,?)",
            (aid, url, title, source, published_at, snippet, lang),
        )
    return aid


def tag_article(aid: str, symbols: list[str]) -> None:
    if not symbols:
        return
    with connect() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO article_symbols(article_id, symbol) VALUES (?,?)",
            [(aid, s) for s in symbols],
        )


def set_sentiment(aid: str, label: str, confidence: float,
                  rationale: str | None = None,
                  model: str = "deepseek-chat") -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO article_sentiment"
            "(article_id, label, confidence, rationale, model) "
            "VALUES (?,?,?,?,?)",
            (aid, label, confidence, rationale, model),
        )


def article_exists(aid: str) -> bool:
    with connect() as conn:
        r = conn.execute("SELECT 1 FROM articles WHERE id=?", (aid,)).fetchone()
    return r is not None


def sentiment_missing() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT a.id, a.title, a.snippet, a.lang "
            "FROM articles a LEFT JOIN article_sentiment s ON s.article_id=a.id "
            "WHERE s.article_id IS NULL "
            "ORDER BY a.published_at DESC LIMIT 200"
        ).fetchall()
    return [dict(r) for r in rows]


def list_news(symbol: str | None = None, since_iso: str | None = None,
              limit: int = 20) -> list[dict[str, Any]]:
    q = ["SELECT a.id, a.url, a.title, a.source, a.published_at, a.snippet, "
         "a.lang, s.label AS sentiment, s.confidence AS sentiment_confidence "
         "FROM articles a "
         "LEFT JOIN article_sentiment s ON s.article_id = a.id"]
    args: list[Any] = []
    where: list[str] = []
    if symbol:
        q.append("JOIN article_symbols x ON x.article_id = a.id")
        where.append("x.symbol = ?")
        args.append(symbol.upper())
    if since_iso:
        where.append("a.published_at >= ?")
        args.append(since_iso)
    if where:
        q.append("WHERE " + " AND ".join(where))
    q.append("ORDER BY a.published_at DESC LIMIT ?")
    args.append(limit)
    with connect() as conn:
        rows = conn.execute(" ".join(q), tuple(args)).fetchall()
    return [dict(r) for r in rows]


_LABEL_VALUE = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}


def sentiment_score(symbol: str, window_hours: int = 24) -> float | None:
    """Weighted mean of label × confidence over window. None if <5 articles."""
    since = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
    with connect() as conn:
        rows = conn.execute(
            "SELECT s.label, s.confidence FROM articles a "
            "JOIN article_symbols x ON x.article_id = a.id "
            "JOIN article_sentiment s ON s.article_id = a.id "
            "WHERE x.symbol = ? AND a.published_at >= ?",
            (symbol.upper(), since),
        ).fetchall()
    if len(rows) < 5:
        return None
    total = sum(_LABEL_VALUE[r["label"]] * float(r["confidence"]) for r in rows)
    return total / len(rows)


def sentiment_summary(symbol: str, window_hours: int = 24 * 7) -> dict[str, Any]:
    since = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
    with connect() as conn:
        rows = conn.execute(
            "SELECT s.label, s.confidence, a.id, a.title, a.url, a.published_at "
            "FROM articles a "
            "JOIN article_symbols x ON x.article_id = a.id "
            "JOIN article_sentiment s ON s.article_id = a.id "
            "WHERE x.symbol = ? AND a.published_at >= ? "
            "ORDER BY a.published_at DESC",
            (symbol.upper(), since),
        ).fetchall()
    count = len(rows)
    if count == 0:
        return {"symbol": symbol.upper(), "window_hours": window_hours,
                "score": None, "count": 0, "positive_pct": 0.0,
                "negative_pct": 0.0, "top_articles": []}
    pos = sum(1 for r in rows if r["label"] == "positive")
    neg = sum(1 for r in rows if r["label"] == "negative")
    score = sum(_LABEL_VALUE[r["label"]] * float(r["confidence"]) for r in rows) / count
    return {
        "symbol": symbol.upper(),
        "window_hours": window_hours,
        "score": score,
        "count": count,
        "positive_pct": pos / count * 100,
        "negative_pct": neg / count * 100,
        "top_articles": [
            {"id": r["id"], "title": r["title"], "url": r["url"],
             "published_at": r["published_at"], "label": r["label"],
             "confidence": r["confidence"]}
            for r in rows[:5]
        ],
    }
