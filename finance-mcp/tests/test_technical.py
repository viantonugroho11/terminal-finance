"""Deterministic-tech smoke tests. Run: pytest -q from finance-mcp/."""
from finance_mcp.models import Candle
from finance_mcp import technical as ta


def _synth(n: int, start: float = 100.0, step: float = 1.0) -> list[Candle]:
    return [
        Candle(date=f"2025-01-{i+1:02d}", open=start + i*step,
               high=start + i*step + 1, low=start + i*step - 1,
               close=start + i*step, volume=1000)
        for i in range(n)
    ]


def test_sma_uptrend():
    c = _synth(30)
    v = ta.sma(c, 20)
    assert v is not None and 118 < v < 122  # mean of last 20 of 100..129


def test_rsi_uptrend_high():
    c = _synth(30)
    r = ta.rsi(c, 14)
    assert r is not None and r > 90  # all-up series → RSI near 100


def test_drawdown_zero_for_monotonic_up():
    c = _synth(30)
    dd = ta.drawdown(c)
    assert dd == 0.0


def test_summary_shape():
    s = ta.summary(_synth(250))
    for k in ("sma_20", "sma_50", "sma_200", "rsi_14", "macd",
              "volatility_30d_annualized_pct", "max_drawdown_pct", "last_close"):
        assert k in s
