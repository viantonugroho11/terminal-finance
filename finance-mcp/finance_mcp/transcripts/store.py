"""Persistence and BM25 search over transcript pages."""
from __future__ import annotations

import hashlib
import re
from typing import Any

from ..portfolio.db import connect

# FTS5 treats these as syntax. A user question is not a query language, so
# they are stripped rather than escaped: "NPL naik?" must not be a parse error.
_FTS_SYNTAX = re.compile(r'["\'()*:^{}\[\]~-]|\bNEAR\b|\bAND\b|\bOR\b|\bNOT\b')


def transcript_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def sanitize_query(q: str) -> str:
    """Turn free text into a safe FTS5 MATCH expression."""
    cleaned = _FTS_SYNTAX.sub(" ", q or "")
    terms = [t for t in cleaned.split() if t]
    # Quote each term individually: this makes every token a literal, so no
    # user text can reach the FTS parser as an operator.
    return " ".join(f'"{t}"' for t in terms)


def exists(url: str) -> bool:
    with connect() as conn:
        return conn.execute(
            "SELECT 1 FROM transcripts WHERE url=?", (url,)
        ).fetchone() is not None


def seen_sha(sha: str) -> str | None:
    """The transcript id already holding these bytes, if any."""
    if not sha:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM transcripts WHERE sha256=?", (sha,)
        ).fetchone()
    return row["id"] if row else None


def save(*, symbol: str, title: str, url: str, category: str | None,
         published_at: str, sha256: str, pages: list[str]) -> dict[str, Any]:
    """Store one transcript and index its pages. Idempotent by url."""
    tid = transcript_id(url)
    non_empty = [(i + 1, t) for i, t in enumerate(pages) if t.strip()]
    with connect() as conn:
        conn.execute(
            "INSERT INTO transcripts"
            " (id, symbol, title, url, category, published_at, sha256, pages)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(url) DO UPDATE SET"
            "   title=excluded.title, category=excluded.category,"
            "   published_at=excluded.published_at, sha256=excluded.sha256,"
            "   pages=excluded.pages, fetched_at=datetime('now')",
            (tid, symbol.upper(), title, url, category, published_at,
             sha256, len(pages)),
        )
        # Replace rather than append, so re-ingesting a corrected file does
        # not leave the old text searchable alongside the new.
        conn.execute("DELETE FROM transcript_pages WHERE transcript_id=?", (tid,))
        conn.execute("DELETE FROM transcript_fts WHERE transcript_id=?", (tid,))
        conn.executemany(
            "INSERT INTO transcript_pages (transcript_id, page, text)"
            " VALUES (?, ?, ?)",
            [(tid, page, text) for page, text in non_empty],
        )
        conn.executemany(
            "INSERT INTO transcript_fts (text, symbol, transcript_id, page)"
            " VALUES (?, ?, ?, ?)",
            [(text, symbol.upper(), tid, page) for page, text in non_empty],
        )
    return {"id": tid, "pages": len(pages), "pages_with_text": len(non_empty)}


def search(symbol: str | None, query: str, top_k: int = 5) -> list[dict]:
    """BM25-ranked pages. Every hit carries page and source url — ADR-0024
    requires a citation, so a result that cannot be cited is not returned."""
    match = sanitize_query(query)
    if not match:
        return []
    sql = (
        "SELECT f.transcript_id, f.page, f.text, bm25(transcript_fts) AS score,"
        "       t.symbol, t.title, t.url, t.published_at"
        "  FROM transcript_fts f"
        "  JOIN transcripts t ON t.id = f.transcript_id"
        " WHERE transcript_fts MATCH ?"
    )
    args: list[Any] = [match]
    if symbol:
        sql += " AND f.symbol = ?"
        args.append(symbol.upper())
    # bm25() returns lower-is-better; sort ascending and flip the sign on the
    # way out so callers see a score that grows with relevance.
    sql += " ORDER BY score LIMIT ?"
    args.append(max(1, min(int(top_k), 50)))

    with connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [
        {"symbol": r["symbol"], "title": r["title"], "url": r["url"],
         "published_at": r["published_at"], "page": r["page"],
         "score": -float(r["score"]),
         "text": r["text"][:1200]}
        for r in rows
    ]


def coverage(symbol: str) -> dict:
    with connect() as conn:
        rows = conn.execute(
            "SELECT title, url, published_at, pages, fetched_at"
            "  FROM transcripts WHERE symbol=?"
            " ORDER BY published_at DESC",
            (symbol.upper(),),
        ).fetchall()
    return {
        "symbol": symbol.upper(),
        "count": len(rows),
        "transcripts": [dict(r) for r in rows],
        "last_ingest": max((r["fetched_at"] for r in rows), default=None),
    }


def latest(symbol: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM transcripts WHERE symbol=?"
            " ORDER BY published_at DESC LIMIT 1",
            (symbol.upper(),),
        ).fetchone()
        if row is None:
            return None
        pages = conn.execute(
            "SELECT page, text FROM transcript_pages"
            " WHERE transcript_id=? ORDER BY page",
            (row["id"],),
        ).fetchall()
    out = dict(row)
    out["page_texts"] = [dict(p) for p in pages]
    return out
