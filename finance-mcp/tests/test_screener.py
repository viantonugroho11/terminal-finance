"""Conversational screener — ADR-0025.

Field names and operators arrive here having been parsed out of natural
language by an LLM, so they are attacker-influenceable in the same way a query
string is. Most of what follows is about that boundary.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

import pytest

os.environ.setdefault(
    "FINANCE_DB", tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
)

from finance_mcp.errors import ErrorCode, FinanceError  # noqa: E402
from finance_mcp.portfolio import db as pdb  # noqa: E402
from finance_mcp.screener import db as scdb  # noqa: E402
from finance_mcp.screener import fields, store  # noqa: E402

TODAY = date.today().isoformat()


def _row(symbol: str, **kw):
    base = {"symbol": symbol, "snapshot_date": TODAY, "market": "IDX",
            "name": symbol, "sector": "Financials", "currency": "IDR"}
    base.update(kw)
    return base


@pytest.fixture
def snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("FINANCE_DB", str(tmp_path / "screen.db"))
    pdb.init(); scdb.init()
    store.upsert(_row("BBCA", price_to_book=4.5, return_on_equity=0.19,
                      dividend_yield=0.025, market_cap=1_100e12))
    store.upsert(_row("BBRI", price_to_book=1.4, return_on_equity=0.17,
                      dividend_yield=0.062, market_cap=700e12))
    store.upsert(_row("BBNI", price_to_book=0.9, return_on_equity=0.11,
                      dividend_yield=0.055, market_cap=200e12))
    store.upsert(_row("NOFUND", market_cap=None))   # metrics missing entirely


# ── the security boundary ──────────────────────────────────────────

@pytest.mark.parametrize("bad", [
    "pbv; DROP TABLE screener_snapshot",
    "1=1",
    "price_to_book) OR (1",
    "captured_at",          # a real column, but not exposed for filtering
    "",
    "../../etc/passwd",
])
def test_unknown_filter_fields_are_refused(snapshot, bad):
    with pytest.raises(FinanceError) as ei:
        store.query([{"field": bad, "op": "<", "value": 2}])
    assert ei.value.code == ErrorCode.SCREENER_FIELD_UNKNOWN
    # The error names what is allowed, so a caller can correct itself.
    assert "known_fields" in ei.value.details


def test_unknown_operators_are_refused(snapshot):
    with pytest.raises(FinanceError) as ei:
        store.query([{"field": "pbv", "op": "OR 1=1 --", "value": 2}])
    assert ei.value.code == ErrorCode.SCREENER_FIELD_UNKNOWN


def test_order_by_goes_through_the_allowlist_too(snapshot):
    """The half that is easy to forget — it looks like formatting."""
    with pytest.raises(FinanceError) as ei:
        store.query(order_by="market_cap; DROP TABLE screener_snapshot")
    assert ei.value.code == ErrorCode.SCREENER_FIELD_UNKNOWN


def test_injection_in_a_value_is_bound_not_executed(snapshot):
    """Values are parameters; a string here must simply match nothing."""
    out = store.query([{"field": "sector", "op": "=",
                        "value": "Financials'; DROP TABLE screener_snapshot; --"}])
    assert out["count"] == 0
    # The table is still there and still populated.
    assert store.query()["count"] == 4


# ── screening behaviour ────────────────────────────────────────────

def test_filters_combine_as_and(snapshot):
    out = store.query([
        {"field": "pbv", "op": "<", "value": 1.5},
        {"field": "div_yield", "op": ">", "value": 0.05},
    ])
    assert [r["symbol"] for r in out["rows"]] == ["BBRI", "BBNI"]


def test_aliases_resolve_to_the_same_column(snapshot):
    a = store.query([{"field": "pbv", "op": "<", "value": 1.5}])
    b = store.query([{"field": "price_to_book", "op": "<", "value": 1.5}])
    assert [r["symbol"] for r in a["rows"]] == [r["symbol"] for r in b["rows"]]


def test_in_operator_accepts_a_list(snapshot):
    out = store.query([{"field": "sector", "op": "in",
                        "value": ["Financials", "Energy"]}])
    assert out["count"] == 4


def test_empty_in_list_matches_nothing_rather_than_erroring(snapshot):
    assert store.query([{"field": "sector", "op": "in", "value": []}])["count"] == 0


def test_rows_missing_the_filtered_metric_are_excluded(snapshot):
    out = store.query([{"field": "roe", "op": ">", "value": 0.0}])
    assert "NOFUND" not in [r["symbol"] for r in out["rows"]]


def test_ordering_puts_nulls_last_in_both_directions(snapshot):
    desc = store.query(order_by="market_cap", desc=True)
    asc = store.query(order_by="market_cap", desc=False)
    assert desc["rows"][0]["symbol"] == "BBCA"
    assert desc["rows"][-1]["symbol"] == "NOFUND"
    # Ascending must not open with the row that has no market cap.
    assert asc["rows"][0]["symbol"] == "BBNI"
    assert asc["rows"][-1]["symbol"] == "NOFUND"


def test_limit_is_clamped(snapshot):
    assert store.query(limit=10_000)["count"] <= 200
    assert store.query(limit=0)["count"] == 1


def test_resnapshotting_the_same_day_replaces(snapshot):
    store.upsert(_row("BBCA", price_to_book=9.9, market_cap=1.0))
    rows = store.query([{"field": "sector", "op": "=", "value": "Financials"}])
    bbca = [r for r in rows["rows"] if r["symbol"] == "BBCA"]
    assert len(bbca) == 1
    assert bbca[0]["price_to_book"] == 9.9


def test_empty_snapshot_reports_itself(monkeypatch, tmp_path):
    monkeypatch.setenv("FINANCE_DB", str(tmp_path / "empty.db"))
    pdb.init(); scdb.init()
    out = store.query()
    assert out["count"] == 0
    assert out["reason"] == "no_snapshot_yet"
    assert out["snapshot_date"] is None


def test_every_allowlisted_field_maps_to_a_real_column(snapshot):
    """Contract test from the spec: no allowlist entry may be a dead name."""
    for name in fields.FIELDS:
        column = fields.resolve(name).column
        assert column in store.COLUMNS, f"{name} -> {column} is not a column"
