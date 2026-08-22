"""Find public-expose filings, fetch them, index their text.

Source is the IDX announcement feed the repo already routes as `disclosures`,
not the per-issuer IR scrapers the spec proposed: one uniform endpoint instead
of one bespoke scraper per issuer.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

import httpx

from ..retry import with_retry
from . import store
from .extract import Extractor, normalize, pypdf_extract

# Titles IDX files these decks under, in both languages. Kept as one pattern
# rather than per-issuer config: the filing titles are standardised even though
# issuer websites are not.
TITLE_PATTERN = re.compile(
    r"paparan\s*publik|public\s*expose|publik\s*expose|analyst\s*meeting|"
    r"public\s*exposé",
    re.IGNORECASE,
)

_MAX_PDF_BYTES = 40 * 1024 * 1024


def looks_like_transcript(title: str) -> bool:
    return bool(TITLE_PATTERN.search(title or ""))


async def _disclosures(symbol: str, limit: int) -> list[dict]:
    from ..registry import router

    async def _fetch(p):
        return await with_retry(lambda: p.disclosures(symbol, limit=limit),
                                provider=p.name, symbol=symbol)

    value, _, _ = await router.call("disclosures", symbol=symbol, fetch=_fetch)
    if value is None:
        return []
    items = value.get("items") if isinstance(value, dict) else getattr(value, "items", [])
    out = []
    for it in items or []:
        out.append(it if isinstance(it, dict) else {
            "date": getattr(it, "date", None), "title": getattr(it, "title", None),
            "category": getattr(it, "category", None), "url": getattr(it, "url", None),
        })
    return out


async def _download(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.content
    if len(data) > _MAX_PDF_BYTES:
        raise ValueError(f"pdf too large: {len(data)} bytes")
    return data


async def ingest_symbol(symbol: str, *, limit: int = 30,
                        extractor: Extractor = pypdf_extract,
                        downloader=None) -> dict:
    """Ingest any new public-expose filings for one symbol."""
    fetch = downloader or _download
    try:
        items = await _disclosures(symbol, limit)
    except Exception as e:
        return {"symbol": symbol.upper(), "ingested": 0,
                "error": f"{type(e).__name__}: {e}"}

    candidates = [
        it for it in items
        if it.get("url") and looks_like_transcript(it.get("title") or "")
    ]
    ingested, skipped, failed = 0, 0, 0
    details: list[dict[str, Any]] = []

    for it in candidates:
        url = it["url"]
        if store.exists(url):
            skipped += 1
            continue
        try:
            data = await fetch(url)
            sha = hashlib.sha256(data).hexdigest()
            # The same deck is often re-filed under a second URL; content
            # hashing catches that, which a URL check alone cannot.
            if store.seen_sha(sha):
                skipped += 1
                continue
            pages = [normalize(p) for p in extractor(data)]
            result = store.save(
                symbol=symbol, title=it.get("title") or "", url=url,
                category=it.get("category"),
                published_at=str(it.get("date") or "")[:10],
                sha256=sha, pages=pages,
            )
            ingested += 1
            details.append({"url": url, **result})
        except Exception as e:
            failed += 1
            details.append({"url": url, "error": f"{type(e).__name__}: {e}"})

    return {"symbol": symbol.upper(), "candidates": len(candidates),
            "ingested": ingested, "skipped": skipped, "failed": failed,
            "details": details}


def tracked_symbols() -> list[str]:
    """Symbols the user follows — watchlists and active watches.

    Deliberately not the whole exchange: a nightly crawl of 435 issuers'
    filings would be a lot of PDFs nobody asked to read.
    """
    from ..portfolio.db import connect
    with connect() as conn:
        rows = conn.execute(
            "SELECT symbol FROM watchlist_items"
            " UNION SELECT symbol FROM watches WHERE disabled=0"
        ).fetchall()
    return sorted({r["symbol"].upper() for r in rows if r["symbol"]})


async def ingest_once(symbols: list[str] | None = None, *,
                      extractor: Extractor = pypdf_extract) -> dict:
    targets = symbols if symbols is not None else tracked_symbols()
    results = [await ingest_symbol(s, extractor=extractor) for s in targets]
    return {"symbols": len(targets),
            "ingested": sum(r.get("ingested", 0) for r in results),
            "results": results}
