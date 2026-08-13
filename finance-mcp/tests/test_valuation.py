"""Reference-vector tests for finance_mcp.valuation. Deterministic math."""
import math
import pytest

from finance_mcp.valuation import (
    capm, wacc, cagr, project_fcf,
    terminal_value_gordon, npv, dcf, sensitivity_table, implied_growth,
)


def approx(a, b, tol=1e-6):
    return math.isclose(a, b, rel_tol=tol, abs_tol=tol)


def test_capm():
    # Cost of equity = 4% + 1.2 * 5% = 10%.
    assert approx(capm(0.04, 1.2, 0.05), 0.10)


def test_wacc_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        wacc(0.10, 0.05, 0.25, 0.5, 0.6)


def test_wacc_standard_case():
    # 60% equity at 10%, 40% debt at 5% after 25% tax.
    # 0.6*0.10 + 0.4*0.05*(1-0.25) = 0.06 + 0.015 = 0.075
    assert approx(wacc(0.10, 0.05, 0.25, 0.6, 0.4), 0.075)


def test_cagr_short_series_returns_none():
    assert cagr([100]) is None


def test_cagr_standard():
    # 100 -> 133.1 over 3 steps: (1.331)^(1/3) - 1 = 0.10.
    assert approx(cagr([100.0, 110.0, 121.0, 133.1]), 0.10, tol=1e-4)


def test_cagr_negative_start_returns_none():
    assert cagr([-100, 200]) is None


def test_project_fcf():
    out = project_fcf(100.0, 0.10, 3)
    assert len(out) == 3
    assert approx(out[0], 110.0)
    assert approx(out[1], 121.0)
    assert approx(out[2], 133.1)


def test_terminal_value_requires_r_gt_g():
    with pytest.raises(ValueError):
        terminal_value_gordon(100.0, 0.10, 0.10)


def test_terminal_value_gordon():
    # FCF_N=100, g=2%, r=10% => 100*1.02 / (0.10-0.02) = 1275
    assert approx(terminal_value_gordon(100.0, 0.02, 0.10), 1275.0)


def test_npv_matches_hand_calc():
    # Two cashflows of 100 at r=10%, periods 1 and 2.
    # PV = 100/1.1 + 100/1.21 = 90.909 + 82.6446 = 173.5537
    assert approx(npv([100.0, 100.0], 0.10), 173.5537, tol=1e-4)


def test_dcf_end_to_end():
    r = dcf(base_fcf=100.0, growth_rate=0.05, years=5,
            discount_rate=0.10, terminal_growth=0.02,
            net_debt=200.0, shares_outstanding=100.0)
    # Projected FCF year1 = 105, year5 = 105 * 1.05^4 = 127.628...
    assert len(r.projected_fcf) == 5
    assert approx(r.projected_fcf[0], 105.0)
    assert approx(r.projected_fcf[-1], 105.0 * (1.05 ** 4))
    # Equity = EV - net_debt.
    assert r.enterprise_value > 0
    assert approx(r.equity_value, r.enterprise_value - 200.0)
    # Per share = equity / 100.
    assert approx(r.per_share_value, r.equity_value / 100.0)
    # PV components sum to EV.
    assert approx(r.pv_explicit + r.pv_terminal, r.enterprise_value)


def test_dcf_without_debt_or_shares_leaves_equity_none():
    r = dcf(100.0, 0.05, 3, 0.10, 0.02)
    assert r.equity_value is None
    assert r.per_share_value is None


def test_dcf_years_must_be_positive():
    with pytest.raises(ValueError):
        dcf(100.0, 0.05, 0, 0.10, 0.02)


def test_sensitivity_table_shape():
    t = sensitivity_table(100.0, 0.05, 5, [0.09, 0.10, 0.11], [0.01, 0.02, 0.03],
                          net_debt=0.0, shares_outstanding=100.0)
    assert t["unit"] == "per_share"
    assert len(t["rows"]) == 3
    assert len(t["rows"][0]["cells"]) == 3
    # Higher discount → lower per-share value at same g.
    v_high_r = t["rows"][2]["cells"][1]["value"]
    v_low_r  = t["rows"][0]["cells"][1]["value"]
    assert v_low_r > v_high_r


def test_sensitivity_table_flags_r_le_g():
    t = sensitivity_table(100.0, 0.05, 5, [0.02], [0.02, 0.05])
    for cell in t["rows"][0]["cells"]:
        assert cell["value"] is None


def test_implied_growth_solves_to_price():
    # Build a scenario, take its per-share value as the "price", then
    # verify implied_growth recovers the original growth.
    base = dcf(base_fcf=10.0, growth_rate=0.08, years=5,
               discount_rate=0.10, terminal_growth=0.03,
               net_debt=0.0, shares_outstanding=1.0)
    price = base.per_share_value
    solved = implied_growth(price, base_fcf_per_share=10.0, years=5,
                            discount_rate=0.10, terminal_growth=0.03)
    assert solved is not None
    assert approx(solved, 0.08, tol=1e-3)


def test_implied_growth_out_of_band_returns_none():
    # Absurd price should not be reachable inside [-0.20, +0.60].
    assert implied_growth(1e18, 10.0, 5, 0.10, 0.03) is None
