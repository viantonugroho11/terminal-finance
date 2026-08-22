"""Public-expose transcript ingest + search — ADR-0024.

Fully offline: the PDF extractor and the downloader are both injected, so no
test touches a real PDF or the network.
"""
from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

os.environ.setdefault(
    "FINANCE_DB", tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
)

from finance_mcp.portfolio import db as pdb  # noqa: E402
from finance_mcp.transcripts import db as trdb  # noqa: E402
from finance_mcp.transcripts import service, store  # noqa: E402
from finance_mcp.transcripts.extract import normalize  # noqa: E402

PAGES = [
    "Paparan Publik BBRI 2026. Agenda dan ringkasan kinerja.",
    "NPL gross turun ke 2,1% dari 2,8% tahun lalu. Coverage ratio 285%.",
    "Dividen payout ratio dinaikkan menjadi 85% untuk tahun buku 2026.",
]


@pytest.fixture
def db(monkeypatch, tmp_path):
    monkeypatch.setenv("FINANCE_DB", str(tmp_path / "tr.db"))
    pdb.init(); trdb.init()


def _save(symbol="BBRI", url="https://idx.co.id/a.pdf", pages=None, sha="sha1"):
    return store.save(symbol=symbol, title="Paparan Publik 2026", url=url,
                      category="Laporan", published_at="2026-08-01",
                      sha256=sha, pages=pages if pages is not None else PAGES)


# ── indexing + citation ────────────────────────────────────────────

def test_search_returns_page_and_source_url(db):
    """ADR-0024: a result that cannot be cited must not be returned."""
    _save()
    hits = store.search("BBRI", "NPL")
    assert len(hits) == 1
    hit = hits[0]
    assert hit["page"] == 2                      # 1-based, as a reader cites
    assert hit["url"] == "https://idx.co.id/a.pdf"
    assert hit["published_at"] == "2026-08-01"
    assert "2,1%" in hit["text"]


def test_ranking_puts_the_better_page_first(db):
    _save()
    hits = store.search("BBRI", "dividen payout")
    assert hits[0]["page"] == 3
    assert hits[0]["score"] >= hits[-1]["score"]  # higher = more relevant


def test_empty_pages_are_not_indexed(db):
    """Scanned decks with no text layer must be visible, not silently empty."""
    out = _save(pages=["", "   ", ""])
    assert out["pages"] == 3
    assert out["pages_with_text"] == 0
    assert store.search("BBRI", "apapun") == []


def test_search_can_span_symbols(db):
    _save(symbol="BBRI", url="https://idx.co.id/a.pdf", sha="a")
    _save(symbol="BBCA", url="https://idx.co.id/b.pdf", sha="b")
    assert len(store.search(None, "NPL")) == 2
    assert len(store.search("BBCA", "NPL")) == 1


# ── the FTS5 query boundary ────────────────────────────────────────

@pytest.mark.parametrize("hostile", [
    'NPL" OR symbol:"',
    "NPL AND (turun OR naik)",
    "NPL*",
    'NPL NEAR/2 "turun"',
    "^NPL",
    "NPL -turun",
])
def test_query_syntax_cannot_reach_the_fts_parser(db, hostile):
    """A user question is not a query language; operators must not parse."""
    _save()
    hits = store.search("BBRI", hostile)      # must not raise
    assert isinstance(hits, list)


def test_blank_query_returns_nothing_rather_than_everything(db):
    _save()
    assert store.search("BBRI", "   ") == []
    assert store.search("BBRI", '"*"') == []


# ── ingest ─────────────────────────────────────────────────────────

def _disclosures(items):
    async def _fn(symbol, limit):
        return items
    return _fn


def _downloader(payload=None):
    """Distinct bytes per URL unless a fixed payload is given.

    Two different filings must not share a hash, or content dedup will
    correctly skip the second and the test would be measuring the fixture.
    """
    async def _fn(url):
        return payload if payload is not None else f"%PDF-{url}".encode()
    return _fn


def test_only_public_expose_filings_are_ingested(db, monkeypatch):
    monkeypatch.setattr(service, "_disclosures", _disclosures([
        {"date": "2026-08-01", "title": "Paparan Publik Tahunan 2026",
         "category": "Laporan", "url": "https://idx.co.id/pp.pdf"},
        {"date": "2026-07-01", "title": "Laporan Keuangan Q2 2026",
         "category": "Laporan", "url": "https://idx.co.id/lk.pdf"},
        {"date": "2026-06-01", "title": "Public Expose Insidentil",
         "category": "Lainnya", "url": "https://idx.co.id/pe.pdf"},
    ]))
    out = asyncio.run(service.ingest_symbol(
        "BBRI", extractor=lambda b: PAGES, downloader=_downloader()))

    assert out["candidates"] == 2      # the financial report is not a deck
    assert out["ingested"] == 2


def test_reingest_skips_urls_already_stored(db, monkeypatch):
    items = [{"date": "2026-08-01", "title": "Paparan Publik",
              "category": None, "url": "https://idx.co.id/pp.pdf"}]
    monkeypatch.setattr(service, "_disclosures", _disclosures(items))
    kw = {"extractor": lambda b: PAGES, "downloader": _downloader()}

    first = asyncio.run(service.ingest_symbol("BBRI", **kw))
    second = asyncio.run(service.ingest_symbol("BBRI", **kw))

    assert first["ingested"] == 1
    assert second["ingested"] == 0 and second["skipped"] == 1


def test_same_deck_refiled_under_a_new_url_is_deduped_by_content(db, monkeypatch):
    """A URL check alone would index the same deck twice."""
    monkeypatch.setattr(service, "_disclosures", _disclosures([
        {"date": "2026-08-01", "title": "Paparan Publik",
         "category": None, "url": "https://idx.co.id/v1.pdf"},
        {"date": "2026-08-02", "title": "Paparan Publik (revisi)",
         "category": None, "url": "https://idx.co.id/v2.pdf"},
    ]))
    # Both URLs serve identical bytes — the same deck, re-filed.
    out = asyncio.run(service.ingest_symbol(
        "BBRI", extractor=lambda b: PAGES,
        downloader=_downloader(b"%PDF-identical")))

    assert out["ingested"] == 1
    assert out["skipped"] == 1


def test_a_failed_download_does_not_abort_the_run(db, monkeypatch):
    monkeypatch.setattr(service, "_disclosures", _disclosures([
        {"date": "2026-08-01", "title": "Paparan Publik A",
         "category": None, "url": "https://idx.co.id/bad.pdf"},
        {"date": "2026-08-02", "title": "Paparan Publik B",
         "category": None, "url": "https://idx.co.id/good.pdf"},
    ]))

    async def flaky(url):
        if "bad" in url:
            raise RuntimeError("404")
        return b"%PDF"

    out = asyncio.run(service.ingest_symbol(
        "BBRI", extractor=lambda b: PAGES, downloader=flaky))

    assert out["failed"] == 1
    assert out["ingested"] == 1


def test_reingesting_replaces_old_page_text(db):
    _save(pages=["harga lama"], sha="v1")
    _save(pages=["harga baru"], sha="v2")     # same url
    assert store.search("BBRI", "lama") == []
    assert len(store.search("BBRI", "baru")) == 1


# ── coverage + latest ──────────────────────────────────────────────

def test_coverage_reports_nothing_without_pretending(db):
    out = store.coverage("BBRI")
    assert out["count"] == 0
    assert out["transcripts"] == []
    assert out["last_ingest"] is None


def test_latest_returns_the_newest_with_its_pages(db):
    _save(url="https://idx.co.id/old.pdf", sha="o")
    store.save(symbol="BBRI", title="Paparan Publik 2027",
               url="https://idx.co.id/new.pdf", category=None,
               published_at="2027-08-01", sha256="n", pages=["halaman baru"])
    latest = store.latest("BBRI")
    assert latest["published_at"] == "2027-08-01"
    assert latest["page_texts"][0]["text"] == "halaman baru"


def test_normalize_collapses_pdf_whitespace():
    assert normalize("NPL\n\n  turun   ke\t2,1%") == "NPL turun ke 2,1%"


def test_title_matching_covers_both_languages():
    for title in ["Paparan Publik Tahunan", "Public Expose 2026",
                  "PUBLIC EXPOSE INSIDENTIL", "Analyst Meeting Q3"]:
        assert service.looks_like_transcript(title)
    for title in ["Laporan Keuangan", "Keterbukaan Informasi", ""]:
        assert not service.looks_like_transcript(title)
