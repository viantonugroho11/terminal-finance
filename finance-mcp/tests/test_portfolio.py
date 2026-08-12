"""Portfolio math — deterministic, no network."""
import os
import tempfile
import pytest

os.environ.setdefault("FINANCE_DB",
                      tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)

from finance_mcp.portfolio import db, service, watchlist  # noqa: E402
db.init()


def _reset():
    with db.cursor() as cur:
        cur.execute("DELETE FROM transactions")
        cur.execute("DELETE FROM accounts")
        cur.execute("DELETE FROM watchlist_items")
        cur.execute("DELETE FROM watchlists")


def test_running_avg_cost_basis():
    _reset()
    service.add_transaction("main", "AAA", "BUY", 10, 100, executed_at="2025-01-01T00:00:00Z")
    service.add_transaction("main", "AAA", "BUY", 10, 200, executed_at="2025-02-01T00:00:00Z")
    raw = service._holdings_raw("main")
    assert raw["AAA"]["quantity"] == 20
    assert raw["AAA"]["cost_basis"] == pytest.approx(3000)  # 10*100 + 10*200
    # partial sell at 250 → realized (250 - 150)*5 = 500
    service.add_transaction("main", "AAA", "SELL", 5, 250, executed_at="2025-03-01T00:00:00Z")
    raw = service._holdings_raw("main")
    assert raw["AAA"]["quantity"] == 15
    assert raw["AAA"]["cost_basis"] == pytest.approx(2250)  # 150 * 15
    assert raw["AAA"]["realized"] == pytest.approx(500)


def test_fee_included_in_cost_basis():
    _reset()
    service.add_transaction("m", "BBB", "BUY", 10, 100, fee=5, executed_at="2025-01-01T00:00:00Z")
    raw = service._holdings_raw("m")
    assert raw["BBB"]["cost_basis"] == pytest.approx(1005)


def test_watchlist_crud():
    _reset()
    watchlist.create("AI")
    watchlist.add("AI", "nvda")
    watchlist.add("AI", "MSFT")
    watchlist.add("AI", "nvda")  # dup ignored
    assert watchlist.items("AI") == ["MSFT", "NVDA"]
    watchlist.remove("AI", "NVDA")
    assert watchlist.items("AI") == ["MSFT"]


def test_closed_position_excluded():
    _reset()
    service.add_transaction("m", "CCC", "BUY", 10, 50, executed_at="2025-01-01T00:00:00Z")
    service.add_transaction("m", "CCC", "SELL", 10, 60, executed_at="2025-02-01T00:00:00Z")
    assert "CCC" not in service._holdings_raw("m")
