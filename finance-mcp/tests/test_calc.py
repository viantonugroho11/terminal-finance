import math
import pytest
from finance_mcp import calc


def test_percentage_change():
    assert calc.percentage_change(100, 110) == pytest.approx(10)
    assert calc.percentage_change(100, 90)  == pytest.approx(-10)
    assert calc.percentage_change(0, 10) is None
    assert calc.percentage_change(None, 10) is None


def test_simple_return():
    assert calc.simple_return(100, 150) == pytest.approx(0.5)
    assert calc.simple_return(0, 10) is None


def test_average_and_none():
    assert calc.average([1, 2, 3, None, 4]) == pytest.approx(2.5)
    assert calc.average([]) is None


def test_weighted_average():
    # 0.5*100 + 0.5*200 = 150
    assert calc.weighted_average([100, 200], [0.5, 0.5]) == pytest.approx(150)
    # zero weights → None
    assert calc.weighted_average([1, 2], [0, 0]) is None
    # length mismatch → None
    assert calc.weighted_average([1, 2, 3], [1, 1]) is None


def test_market_cap_and_ev():
    mc = calc.market_cap(1_000_000, 50)
    assert mc == 50_000_000
    ev = calc.enterprise_value(mc, total_debt=5_000_000, cash=1_000_000)
    assert ev == 54_000_000
    assert calc.enterprise_value(None, 1, 1) is None


def test_cagr():
    # 100 → 200 over 5 years → 2^(1/5) - 1
    v = calc.cagr(100, 200, 5)
    assert v == pytest.approx(2 ** 0.2 - 1)
    assert calc.cagr(0, 100, 1) is None
    assert calc.cagr(100, -1, 1) is None
