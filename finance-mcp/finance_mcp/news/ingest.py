"""RSS ingest — one pass over configured sources.

Uses feedparser if available; otherwise falls back to a minimal RSS
parser sufficient for well-formed feeds. Keeps ingest usable in test
envs where the optional dep isn't installed.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from xml.etree import ElementTree as ET

import httpx

from . import store, tagger
from .sources import SOURCES, Source


@dataclass
class IngestReport:
    source: str
    fetched: int
    new: int
    tagged: int
    error: str | None = None


_TAG_STRIP = re.compile(r"<[^>]+>")


def _clean(s: str | None) -> str:
    if not s:
        return ""
    return _TAG_STRIP.sub(" ", s).strip()


def _parse_rss(xml_text: str) -> list[dict[str, Any]]:
    """Minimal RSS 2.0 + Atom fallback parser."""
    items: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        title = _clean(it.findtext("title"))
        desc = _clean(it.findtext("description"))
        pub = (it.findtext("pubDate") or "").strip()
        if link and title:
            items.append({"link": link, "title": title, "snippet": desc, "pub": pub})
    for it in root.iter(f"{{{ns['atom']}}}entry"):
        link_el = it.find(f"{{{ns['atom']}}}link")
        link = link_el.get("href") if link_el is not None else ""
        title = _clean(it.findtext(f"{{{ns['atom']}}}title"))
        summary = _clean(it.findtext(f"{{{ns['atom']}}}summary"))
        pub = (it.findtext(f"{{{ns['atom']}}}updated")
               or it.findtext(f"{{{ns['atom']}}}published") or "").strip()
        if link and title:
            items.append({"link": link, "title": title, "snippet": summary, "pub": pub})
    return items


def _normalize_published(raw: str) -> str:
    if not raw:
        return datetime.now(timezone.utc).isoformat()
    for fmt in ("%a, %d %b %Y %H:%M:%S %z",
                "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    return datetime.now(timezone.utc).isoformat()


async def _fetch(source: Source, client: httpx.AsyncClient) -> str:
    r = await client.get(source.url, timeout=15.0, follow_redirects=True,
                         headers={"User-Agent": "finance-mcp/0.2"})
    r.raise_for_status()
    return r.text


async def ingest_source(source: Source, *,
                        fetcher: Callable | None = None) -> IngestReport:
    try:
        if fetcher is not None:
            xml_text = await fetcher(source)
        else:
            async with httpx.AsyncClient() as client:
                xml_text = await _fetch(source, client)
    except Exception as e:
        return IngestReport(source.name, 0, 0, 0, error=f"{type(e).__name__}: {e}")

    items = _parse_rss(xml_text)
    new_ct = tag_ct = 0
    for it in items:
        aid = store.article_id(it["link"])
        if store.article_exists(aid):
            continue
        pub = _normalize_published(it["pub"])
        store.insert_article(
            url=it["link"], title=it["title"], source=source.name,
            published_at=pub, snippet=it["snippet"][:500], lang=source.lang,
        )
        new_ct += 1
        syms = tagger.tag(f"{it['title']} {it['snippet']}")
        if syms:
            store.tag_article(aid, syms)
            tag_ct += 1
    return IngestReport(source.name, len(items), new_ct, tag_ct)


async def ingest_all(*, fetcher: Callable | None = None) -> list[IngestReport]:
    return [await ingest_source(s, fetcher=fetcher) for s in SOURCES]
