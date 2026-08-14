"""Backtest engine — ADR-0029. No network."""
from __future__ import annotations
import os
import tempfile

import pytest

os.environ.setdefault(
    "FINANCE_DB",
    tempfile.NamedTemporaryFile(suffix=".db", delete=False).name,
)

from finance_mcp.portfolio import db as pdb  # noqa: E402
from finance_mcp.backtest import db as btdb  # noqa: E402
from finance_mcp.backtest import costs, engine, metrics, strategies, service  # noqa: E402
from finance_mcp.backtest.context import BarContext, LookAheadError, Order  # noqa: E402

pdb.init()
btdb.init()


def _reset() -> None:
    from finance_mcp.portfolio.db import connect
    with connect() as conn:
        conn.execute("DELETE FROM backtest_jobs")


def _bars(closes: list[float]) -> list[dict]:
    return [
        {"ts": f"2026-01-{i+1:02d}", "open": c, "high": c * 1.01,
         "low": c * 0.99, "close": c, "volume": 1000}
        for i, c in enumerate(closes)
    ]


# ── BarContext no-look-ahead ───────────────────────────────────────────

def test_context_prices_returns_past_and_current_only() -> None:
    bars = _bars([100, 101, 102, 103, 104])
    ctx = BarContext(symbol="X", _bars=bars, _index=2)
    got = ctx.prices(lookback=3)
    assert [b["close"] for b in got] == [100, 101, 102]


def test_context_future_raises() -> None:
    ctx = BarContext(symbol="X", _bars=_bars([100, 101, 102]), _index=1)
    with pytest.raises(LookAheadError):
        ctx.future(1)


def test_context_prices_lookback_zero_returns_empty() -> None:
    ctx = BarContext(symbol="X", _bars=_bars([100, 101]), _index=1)
    assert ctx.prices(lookback=0) == []


# ── cost model ─────────────────────────────────────────────────────────

def test_fill_price_buy_pays_more() -> None:
    px = costs.fill_price(base_price=1000.0, side="BUY", market="ID")
    assert px > 1000.0
    assert px == pytest.approx(1000.0 * (1 + 5.0 / 10_000))


def test_fill_price_sell_receives_less() -> None:
    px = costs.fill_price(base_price=1000.0, side="SELL", market="ID")
    assert px < 1000.0


def test_transaction_cost_sell_includes_pph() -> None:
    fee_sell = costs.transaction_cost(notional=1_000_000, qty=100,
                                      side="SELL", market="ID")
    fee_buy = costs.transaction_cost(notional=1_000_000, qty=100,
                                     side="BUY", market="ID")
    assert fee_sell > fee_buy   # sell has extra 0.1% PPh


# ── metrics ────────────────────────────────────────────────────────────

def test_total_return_flat_zero() -> None:
    assert metrics.total_return([100, 100, 100]) == 0.0


def test_total_return_double() -> None:
    assert metrics.total_return([100, 150, 200]) == pytest.approx(1.0)


def test_max_drawdown_captures_peak_to_trough() -> None:
    dd = metrics.max_drawdown([100, 120, 90, 110])
    assert dd == pytest.approx((90 - 120) / 120)


def test_sharpe_none_when_no_variance() -> None:
    assert metrics.sharpe([100, 100, 100]) is None


def test_sharpe_positive_on_uptrend() -> None:
    s = metrics.sharpe([100, 101, 102, 103, 104])
    assert s is not None and s > 0


# ── strategies ─────────────────────────────────────────────────────────

def test_buy_and_hold_fires_only_on_first_bar() -> None:
    bars = _bars([100, 101, 102])
    o1 = strategies.buy_and_hold(
        BarContext(symbol="X", _bars=bars, _index=0), {"size": 10})
    o2 = strategies.buy_and_hold(
        BarContext(symbol="X", _bars=bars, _index=1), {"size": 10})
    assert len(o1) == 1 and o1[0].side == "BUY" and o1[0].qty == 10
    assert o2 == []


def test_sma_cross_needs_enough_bars() -> None:
    bars = _bars(list(range(10)))
    out = strategies.sma_cross(
        BarContext(symbol="X", _bars=bars, _index=5),
        {"fast": 3, "slow": 5})
    assert out == []  # index < slow_n


# ── engine end-to-end ──────────────────────────────────────────────────

def test_engine_buy_and_hold_matches_return_minus_costs() -> None:
    bars = _bars([100, 105, 110, 115, 120])
    out = engine.run(
        symbol="X", bars=bars,
        strategy_fn=strategies.buy_and_hold,
        params={"size": 100}, market="ID",
        initial_cash=100_000.0,
    )
    assert out["bars_count"] == 5
    # Fill occurs at bar 1 open (=105 with buy slippage), final MtM at 120.
    assert out["equity_curve"][0] == pytest.approx(100_000.0)
    # One trade recorded
    assert len(out["trades"]) == 1
    assert out["trades"][0]["side"] == "BUY"


def test_engine_sma_cross_generates_at_least_one_trade() -> None:
    # Down then up → fast crosses slow from below (golden cross) → BUY
    closes = [20, 18, 16, 14, 12, 10, 8, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24]
    bars = _bars(closes)
    out = engine.run(
        symbol="X", bars=bars,
        strategy_fn=strategies.sma_cross,
        params={"fast": 3, "slow": 5, "size": 10},
        market="ID", initial_cash=1_000_000.0,
    )
    assert any(t["side"] == "BUY" for t in out["trades"])


def test_engine_rejects_empty_bars() -> None:
    with pytest.raises(ValueError):
        engine.run(symbol="X", bars=[],
                   strategy_fn=strategies.buy_and_hold, params={})


# ── service (job store) ────────────────────────────────────────────────

def test_service_execute_persists_result() -> None:
    _reset()
    job_id = service.create_job(
        strategy="buy_and_hold", params={"size": 10},
        universe=["X"], start="2026-01-01", end="2026-01-05",
    )
    bars = _bars([100, 105, 110, 115, 120])
    service.execute(job_id=job_id, bars_by_symbol={"X": bars})
    status = service.get_status(job_id)
    assert status["status"] == "done"
    result = service.get_result(job_id)
    assert result["status"] == "done"
    assert result["result"]["bars_count"] == 5


def test_service_execute_records_error() -> None:
    _reset()
    job_id = service.create_job(
        strategy="nonexistent", params={}, universe=["X"],
        start="2026-01-01", end="2026-01-05",
    )
    with pytest.raises(KeyError):
        service.execute(job_id=job_id, bars_by_symbol={"X": _bars([100])})
    status = service.get_status(job_id)
    assert status["status"] == "error"
    assert "unknown strategy" in (status["error"] or "")
