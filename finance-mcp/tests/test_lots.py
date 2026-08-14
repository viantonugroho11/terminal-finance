"""ADR-0027 — lot store, FIFO/HIFO, tax, rebalance."""
from __future__ import annotations
import os
import tempfile
from datetime import datetime, timezone

import pytest

os.environ.setdefault(
    "FINANCE_DB",
    tempfile.NamedTemporaryFile(suffix=".db", delete=False).name,
)

from finance_mcp.portfolio import db as pdb, lots as plots  # noqa: E402
from finance_mcp.portfolio import lots_calc as plcalc  # noqa: E402
from finance_mcp.portfolio import rebalance as preb  # noqa: E402
from finance_mcp.portfolio import tax as ptax  # noqa: E402

pdb.init()
plots.init()


def _reset() -> None:
    from finance_mcp.portfolio.db import connect
    with connect() as conn:
        conn.execute("DELETE FROM lot_closes")
        conn.execute("DELETE FROM lots")


def _iso(offset_days: int = 0) -> str:
    from datetime import timedelta
    return (datetime(2026, 1, 1, tzinfo=timezone.utc)
            + timedelta(days=offset_days)).isoformat()


# ── tax constants ──────────────────────────────────────────────────────

def test_tax_id_equity_sell_rate() -> None:
    t = ptax.tax_on_sell(asset_class="EQUITY_ID", gross_proceeds=1_000_000)
    assert t == pytest.approx(1_000)  # 0.1%


def test_tax_id_crypto_sell_includes_ppn() -> None:
    t = ptax.tax_on_sell(asset_class="CRYPTO", gross_proceeds=1_000_000)
    assert t == pytest.approx(2_200)  # 0.11% + 0.11%


def test_tax_us_regime_zero_on_sell() -> None:
    t = ptax.tax_on_sell(asset_class="EQUITY_US",
                         gross_proceeds=1_000_000, regime="US")
    assert t == 0.0


# ── lot CRUD ───────────────────────────────────────────────────────────

def test_buy_then_positions() -> None:
    _reset()
    plots.record_buy(plots.Lot(symbol="BBCA", qty=100, price=9500,
                               acquired_at=_iso(0), fee=5000))
    plots.record_buy(plots.Lot(symbol="BBCA", qty=200, price=9800,
                               acquired_at=_iso(1)))
    pos = plots.positions()
    assert pos["BBCA"]["qty"] == 300
    # cost = 100*9500 + 5000 fee + 200*9800 = 950000+5000+1960000 = 2915000
    assert pos["BBCA"]["cost_basis"] == pytest.approx(2_915_000)


def test_sell_negative_qty_raises() -> None:
    _reset()
    with pytest.raises(ValueError):
        plots.record_sell(symbol="BBCA", qty=-1, price=1,
                          closed_at=_iso())


def test_sell_exceeds_position_raises() -> None:
    _reset()
    plots.record_buy(plots.Lot(symbol="BBCA", qty=10, price=100,
                               acquired_at=_iso()))
    with pytest.raises(ValueError):
        plots.record_sell(symbol="BBCA", qty=20, price=110,
                          closed_at=_iso(1))


# ── FIFO / HIFO ────────────────────────────────────────────────────────

def test_fifo_closes_oldest_lot_first() -> None:
    _reset()
    plots.record_buy(plots.Lot(symbol="BBCA", qty=10, price=100,
                               acquired_at=_iso(0)))
    plots.record_buy(plots.Lot(symbol="BBCA", qty=10, price=200,
                               acquired_at=_iso(1)))
    closes = plots.record_sell(symbol="BBCA", qty=15, price=250,
                               closed_at=_iso(2), method="FIFO")
    # Should exhaust lot 1 (10 shares @100), then 5 from lot 2 @200
    assert sum(c.qty for c in closes) == 15
    remaining = plots.positions()["BBCA"]["qty"]
    assert remaining == 5


def test_hifo_closes_highest_cost_first() -> None:
    _reset()
    plots.record_buy(plots.Lot(symbol="BBCA", qty=10, price=100,
                               acquired_at=_iso(0)))
    plots.record_buy(plots.Lot(symbol="BBCA", qty=10, price=200,
                               acquired_at=_iso(1)))
    plots.record_sell(symbol="BBCA", qty=8, price=250,
                      closed_at=_iso(2), method="HIFO")
    # Lot @200 has qty_remaining = 2; lot @100 untouched
    all_ = plots.list_lots(open_only=False)
    per_price = {row["price"]: row["qty_remaining"] for row in all_}
    assert per_price[200.0] == 2
    assert per_price[100.0] == 10


# ── PnL ────────────────────────────────────────────────────────────────

def test_unrealized_pnl_uses_supplied_quotes() -> None:
    _reset()
    plots.record_buy(plots.Lot(symbol="BBCA", qty=100, price=9500,
                               acquired_at=_iso()))
    out = plcalc.unrealized_pnl({"BBCA": 9800.0})
    row = out["positions"][0]
    assert row["symbol"] == "BBCA"
    assert row["market_value"] == pytest.approx(980_000)
    assert row["unrealized_pnl"] == pytest.approx(30_000)


def test_unrealized_pnl_missing_quote_returns_null_price() -> None:
    _reset()
    plots.record_buy(plots.Lot(symbol="BBCA", qty=100, price=9500,
                               acquired_at=_iso()))
    out = plcalc.unrealized_pnl({})
    row = out["positions"][0]
    assert row["price"] is None
    assert row["unrealized_pnl"] is None


def test_realized_pnl_id_regime_applies_pph() -> None:
    _reset()
    plots.record_buy(plots.Lot(symbol="BBCA", qty=100, price=9500,
                               acquired_at=_iso(0)))
    plots.record_sell(symbol="BBCA", qty=100, price=9800,
                      closed_at=_iso(1))
    out = plcalc.realized_pnl(regime="ID")
    row = out["positions"][0]
    # gross PnL = (9800-9500)*100 = 30_000
    assert row["pnl_gross"] == pytest.approx(30_000)
    # PPh 0.1% on 100 * 9800 = 980
    assert row["tax_regime"] == pytest.approx(980)
    assert row["pnl_after_tax"] == pytest.approx(30_000 - 980)


# ── Rebalance ──────────────────────────────────────────────────────────

def test_rebalance_targets_must_sum_to_one() -> None:
    with pytest.raises(ValueError):
        preb.rebalance_plan(targets={"BBCA": 0.5, "BBRI": 0.3},
                            quotes={"BBCA": 100, "BBRI": 100})


def test_rebalance_generates_trades_within_tolerance() -> None:
    _reset()
    plots.record_buy(plots.Lot(symbol="BBCA", qty=100, price=100,
                               acquired_at=_iso()))
    # Current: 100% BBCA @ 10_000. Target: 60% BBCA + 40% cash.
    plan = preb.rebalance_plan(
        targets={"BBCA": 0.6, "CASH": 0.4},
        quotes={"BBCA": 100.0, "CASH": 1.0},
        cash=0.0, tolerance=0.02,
    )
    bbca_trade = [t for t in plan["trades"] if t["symbol"] == "BBCA"]
    assert len(bbca_trade) == 1
    assert bbca_trade[0]["side"] == "SELL"
    # Should sell ~40 shares (40% of 100)
    assert 30 <= bbca_trade[0]["qty"] <= 50


def test_rebalance_skips_within_tolerance() -> None:
    _reset()
    plots.record_buy(plots.Lot(symbol="BBCA", qty=100, price=100,
                               acquired_at=_iso()))
    plan = preb.rebalance_plan(
        targets={"BBCA": 1.0},
        quotes={"BBCA": 100.0},
        tolerance=0.02,
    )
    assert plan["trades"] == []


def test_rebalance_sell_reports_tax_cost() -> None:
    _reset()
    plots.record_buy(plots.Lot(symbol="BBCA", qty=100, price=100,
                               acquired_at=_iso()))
    plan = preb.rebalance_plan(
        targets={"BBCA": 0.5, "CASH": 0.5},
        quotes={"BBCA": 100.0, "CASH": 1.0},
        regime="ID",
    )
    sell = [t for t in plan["trades"] if t["side"] == "SELL"][0]
    # tax = 0.001 * notional
    assert sell["tax_cost"] == pytest.approx(sell["notional"] * 0.001)
