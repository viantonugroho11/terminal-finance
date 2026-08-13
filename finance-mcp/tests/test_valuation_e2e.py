"""End-to-end DCF tools under FINANCE_PROVIDER=mock."""
import asyncio
import os
import tempfile

os.environ["FINANCE_PROVIDER"] = "mock"
os.environ.setdefault("FINANCE_DB",
                      tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)

from finance_mcp import server  # noqa: E402


def _run(coro): return asyncio.run(coro)


def _ok(r):
    assert "error" not in r, r
    return r["data"]


def test_valuation_dcf_returns_full_shape():
    d = _ok(_run(server.valuation_dcf("NVDA")))
    assert d["symbol"] == "NVDA"
    inp = d["inputs"]
    for k in ("base_fcf", "growth_rate", "discount_rate",
              "terminal_growth", "beta_used"):
        assert k in inp
    assert isinstance(d["projected_fcf"], list) and len(d["projected_fcf"]) == 5
    assert d["enterprise_value"] > 0
    assert d["terminal_value"] > 0
    assert d["pv_terminal"] > 0
    assert d["upside_vs_market_cap"] is None or isinstance(
        d["upside_vs_market_cap"], float)


def test_valuation_dcf_honors_overrides():
    d = _ok(_run(server.valuation_dcf("NVDA", discount_rate=0.15,
                                       terminal_growth=0.02,
                                       growth_rate=0.08,
                                       projection_years=7)))
    inp = d["inputs"]
    assert inp["discount_rate"] == 0.15
    assert inp["terminal_growth"] == 0.02
    assert inp["growth_rate"] == 0.08
    assert inp["projection_years"] == 7
    assert len(d["projected_fcf"]) == 7


def test_valuation_sensitivity_grid_shape():
    d = _ok(_run(server.valuation_sensitivity("NVDA")))
    assert d["symbol"] == "NVDA"
    assert d["unit"] in ("per_share", "enterprise_value")
    assert len(d["rows"]) == 5  # 5 default discount rates
    assert len(d["rows"][0]["cells"]) == 4  # 4 default terminal growths


def test_valuation_dcf_idr_symbol_still_computes():
    d = _ok(_run(server.valuation_dcf("BBCA")))
    # Router resolves BBCA -> IDX -> mock (only mock registered under mock provider).
    assert d["symbol"] == "BBCA"
    assert d["enterprise_value"] > 0
