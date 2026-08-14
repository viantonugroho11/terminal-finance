"""RSS source registry — ADR-0028 v1 list."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    lang: str = "id"


SOURCES: list[Source] = [
    Source("kontan",       "https://www.kontan.co.id/rss",             "id"),
    Source("bisnis",       "https://www.bisnis.com/rss",               "id"),
    Source("idnfinancials","https://www.idnfinancials.com/rss/news",   "en"),
    Source("reuters_biz",  "https://www.reutersagency.com/feed/?best-sectors=business-finance&post_type=best", "en"),
    Source("cnbc_markets", "https://www.cnbc.com/id/15839069/device/rss/rss.html", "en"),
    Source("idx_press",    "https://www.idx.co.id/id/rss/news",        "id"),
]


def by_name(name: str) -> Source | None:
    for s in SOURCES:
        if s.name == name:
            return s
    return None
