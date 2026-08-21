"""Watch engine — ADR-0023 unit tests. No network."""
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

from finance_mcp.portfolio import db as pdb  # noqa: E402
from finance_mcp.watch import db as wdb  # noqa: E402
from finance_mcp.watch import evaluator, metrics, rules, store

pdb.init()
wdb.init()


def _reset() -> None:
    from finance_mcp.portfolio.db import connect
    with connect() as conn:
        conn.execute("DELETE FROM watch_events")
        conn.execute("DELETE FROM watches")


# ── rules ──────────────────────────────────────────────────────────────

def test_rule_validation_op() -> None:
    with pytest.raises(ValueError):
        rules.Rule(symbol="BBCA", metric="price_change_pct_intraday",
                   op="!!", threshold=-2.0)


def test_rule_validation_metric() -> None:
    with pytest.raises(ValueError):
        rules.Rule(symbol="BBCA", metric="not_a_metric",
                   op="<", threshold=-2.0)


def test_rule_macro_metric_allowed() -> None:
    r = rules.Rule(symbol="ID", metric="macro_release:cpi",
                   op=">", threshold=0.0)
    assert r.metric == "macro_release:cpi"


def test_parse_nl_intraday_drop() -> None:
    r = rules.parse_nl("kabari kalau BBCA turun >2%")
    assert r.symbol == "BBCA"
    assert r.metric == "price_change_pct_intraday"
    assert r.op == "<"
    assert r.threshold == -2.0


def test_parse_nl_volume() -> None:
    r = rules.parse_nl("pantau volume TLKM 2x")
    assert r.symbol == "TLKM"
    assert r.metric == "volume_vs_ma20"
    assert r.op == ">"
    assert r.threshold == 2.0


def test_parse_nl_no_ticker_raises() -> None:
    with pytest.raises(ValueError):
        rules.parse_nl("kabari kalau turun")


# ── store ──────────────────────────────────────────────────────────────

def test_store_crud_and_disable() -> None:
    _reset()
    r = rules.Rule(symbol="BBCA", metric="price_change_pct_intraday",
                   op="<", threshold=-2.0, cooldown_sec=60)
    store.add(r)
    assert store.get(r.id).symbol == "BBCA"

    all_ = store.list_all()
    assert len(all_) == 1
    assert not all_[0].disabled

    store.set_disabled(r.id, True)
    assert store.get(r.id).disabled

    assert store.delete(r.id)
    assert store.get(r.id) is None


def test_eligible_respects_cooldown() -> None:
    _reset()
    r = rules.Rule(symbol="BBCA", metric="price_change_pct_intraday",
                   op="<", threshold=-2.0, cooldown_sec=3600)
    store.add(r)
    # Never fired → eligible.
    assert any(x.id == r.id for x in store.eligible_now(
        datetime.now(timezone.utc).isoformat()))

    # Record a fire just now → not eligible for another hour.
    store.record_fire(r.id, -3.0, delivered=True)
    assert not any(x.id == r.id for x in store.eligible_now(
        datetime.now(timezone.utc).isoformat()))

    # Fast-forward 2h → eligible again.
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    assert any(x.id == r.id for x in store.eligible_now(future))


# ── metrics.compare ────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "op,value,threshold,expected",
    [
        (">", 3.0, 2.0, True),
        ("<", 1.0, 2.0, True),
        (">=", 2.0, 2.0, True),
        ("<=", 2.0, 2.0, True),
        ("==", 2.0, 2.0, True),
        (">", 1.0, 2.0, False),
        ("<", 3.0, 2.0, False),
    ],
)
def test_compare(op: str, value: float, threshold: float, expected: bool) -> None:
    assert metrics.compare(op, value, threshold) is expected


# ── evaluator (injected sender, injected metric) ───────────────────────

async def _fake_sender_ok(text: str, chat_id: str | None) -> tuple[bool, str | None]:
    _fake_sender_ok.calls.append((text, chat_id))  # type: ignore[attr-defined]
    return True, None


_fake_sender_ok.calls = []  # type: ignore[attr-defined]


def test_evaluate_rule_fires(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset()
    r = rules.Rule(symbol="BBCA", metric="price_change_pct_intraday",
                   op="<", threshold=-2.0, cooldown_sec=10)
    store.add(r)

    async def fake_resolve(metric: str, symbol: str) -> float | None:
        return -3.5

    monkeypatch.setattr(metrics, "resolve", fake_resolve)
    _fake_sender_ok.calls = []  # type: ignore[attr-defined]

    result = asyncio.run(
        evaluator.evaluate_rule(r, sender=_fake_sender_ok)
    )
    assert result["status"] == "fired"
    assert result["delivered"] is True
    assert len(_fake_sender_ok.calls) == 1  # type: ignore[attr-defined]

    # last_fired_at bumped
    assert store.get(r.id).last_fired_at is not None


def test_evaluate_rule_no_trigger(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset()
    r = rules.Rule(symbol="BBCA", metric="price_change_pct_intraday",
                   op="<", threshold=-5.0)
    store.add(r)

    async def fake_resolve(metric: str, symbol: str) -> float | None:
        return -1.0  # above threshold, so `<` fails

    monkeypatch.setattr(metrics, "resolve", fake_resolve)
    result = asyncio.run(evaluator.evaluate_rule(r, sender=_fake_sender_ok))
    assert result["status"] == "no_trigger"


def test_evaluate_rule_skipped_when_metric_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset()
    r = rules.Rule(symbol="BBCA", metric="price_change_pct_intraday",
                   op="<", threshold=-2.0)
    store.add(r)

    async def fake_resolve(metric: str, symbol: str) -> float | None:
        return None

    monkeypatch.setattr(metrics, "resolve", fake_resolve)
    result = asyncio.run(evaluator.evaluate_rule(r, sender=_fake_sender_ok))
    assert result["status"] == "skipped"
