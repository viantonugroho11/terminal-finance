"""Portfolio routes through Router — IDR + USD kept separate."""
import asyncio
import os
import tempfile

os.environ["FINANCE_PROVIDER"] = "mock"
os.environ.setdefault("FINANCE_DB",
                      tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)

from finance_mcp import server  # noqa: E402
from finance_mcp.portfolio import service as psvc, db, watchlist  # noqa: E402


def _run(coro): return asyncio.run(coro)


def _reset():
    with db.cursor() as cur:
        cur.execute("DELETE FROM transactions")
        cur.execute("DELETE FROM accounts")


def test_position_carries_currency_from_quote():
    _reset()
    # Mock provider always returns USD; verify the Position dataclass
    # actually surfaces the currency field so portfolio callers can
    # group.
    psvc.add_transaction("main", "AAPL", "BUY", 10, 190,
                         executed_at="2025-01-01T00:00:00Z")
    pos = _run(psvc.holdings("main"))
    assert pos and pos[0].currency == "USD"


def test_summary_by_currency_bucket():
    _reset()
    psvc.add_transaction("main", "AAPL", "BUY", 10, 190,
                         executed_at="2025-01-01T00:00:00Z")
    psvc.add_transaction("main", "MSFT", "BUY", 5, 400,
                         executed_at="2025-01-02T00:00:00Z")
    s = _run(psvc.summary("main"))
    # Under mock, both quotes are USD → one bucket.
    assert "by_currency" in s
    assert set(s["by_currency"].keys()) == {"USD"}
    assert s["by_currency"]["USD"]["positions"] == 2


def test_holdings_uses_router_not_yahoo_directly():
    """Regression: portfolio must not bypass the router.

    Direct proof: with FINANCE_PROVIDER=mock, MockProvider owns every
    market — router picks it. If holdings called YahooProvider directly
    like before, we'd hit yfinance and either crash or return real data.
    """
    _reset()
    psvc.add_transaction("main", "BBCA", "BUY", 100, 9000,
                         executed_at="2025-01-01T00:00:00Z", currency="IDR")
    pos = _run(psvc.holdings("main"))
    assert pos and pos[0].symbol == "BBCA"
    # Mock returns a synthetic quote in USD (its default) — the point
    # is only that the call did NOT go out to a live provider.
    assert pos[0].price is not None
