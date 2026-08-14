"""Morning digest composer — ADR-0023."""
from __future__ import annotations
import os
import tempfile

os.environ.setdefault(
    "FINANCE_DB",
    tempfile.NamedTemporaryFile(suffix=".db", delete=False).name,
)

from finance_mcp import digest  # noqa: E402


_PAYLOAD = {
    "generated_at": "2026-08-14T00:30:00+00:00",
    "ihsg": {"last": 7412.5, "change_pct": 1.23},
    "us_overnight": {"spx_change_pct": 0.45, "ndx_change_pct": 0.72},
    "fx": {"dxy": 103.21, "usdidr": 15980.0},
    "macro": {"bi_rate": 6.25},
    "movers": [
        {"symbol": "GOTO", "change_pct": 4.5},
        {"symbol": "BBRI", "change_pct": 2.1},
    ],
    "foreign_flow": [
        {"symbol": "BBCA", "net_idr": 250_000_000_000},
        {"symbol": "TLKM", "net_idr": -85_000_000_000},
    ],
    "watchlist": [
        {"symbol": "BBCA", "last": 9500, "change_pct": 0.5},
    ],
}


def test_render_id_contains_sections() -> None:
    out = digest.render(_PAYLOAD, lang="id")
    assert "Morning Digest" in out
    assert "IHSG" in out
    assert "Top movers IDX" in out
    assert "BBCA" in out
    assert "BI Rate" in out


def test_render_en_translates_headers() -> None:
    out = digest.render(_PAYLOAD, lang="en")
    assert "IDX Top Movers" in out
    assert "Foreign Net Flow" in out


def test_render_under_telegram_cap() -> None:
    fat = dict(_PAYLOAD)
    fat["movers"] = [{"symbol": f"SYM{i}", "change_pct": i * 0.1}
                     for i in range(500)]
    fat["watchlist"] = [{"symbol": f"WL{i}", "last": 100.0, "change_pct": 0.0}
                        for i in range(500)]
    out = digest.render(fat, lang="id")
    assert len(out) <= digest.TELEGRAM_CAP


def test_render_handles_missing_sections() -> None:
    minimal = {
        "generated_at": "2026-08-14T00:00:00+00:00",
        "ihsg": {},
        "us_overnight": {},
        "fx": {},
        "macro": {},
        "movers": [],
        "foreign_flow": [],
        "watchlist": [],
    }
    out = digest.render(minimal, lang="id")
    assert "Morning Digest" in out
    assert "—" in out  # placeholder for missing IHSG
