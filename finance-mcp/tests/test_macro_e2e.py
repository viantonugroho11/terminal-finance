"""End-to-end macro tool under FINANCE_PROVIDER=mock."""
import asyncio
import os
import tempfile

os.environ["FINANCE_PROVIDER"] = "mock"
os.environ.setdefault("FINANCE_DB",
                      tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)

from finance_mcp import server  # noqa: E402


def _run(coro): return asyncio.run(coro)


def test_get_macro_bi_rate():
    r = _run(server.get_macro("bi_rate"))
    assert "error" not in r, r
    d = r["data"]
    assert d["indicator"] == "bi_rate"
    assert d["source"] == "mock"
    assert d["unit"] == "%"
    assert len(d["observations"]) == 3
    assert r["provenance"]["source"] == "mock"


def test_get_macro_jisdor():
    r = _run(server.get_macro("jisdor"))
    assert "error" not in r
    assert r["data"]["unit"] == "IDR/USD"


def test_get_macro_alias_fx_usd_idr():
    r = _run(server.get_macro("fx_usd_idr"))
    assert "error" not in r
    # Mock echoes the requested indicator name.
    assert r["data"]["indicator"].lower() in ("fx_usd_idr", "jisdor")


def test_get_macro_unknown_indicator_errors_cleanly():
    r = _run(server.get_macro("does_not_exist"))
    assert "error" in r
    assert r["error"]["code"] == "DATA_UNAVAILABLE"


def test_get_macro_banking_spi_via_mock():
    r = _run(server.get_macro("banking_spi"))
    assert "error" not in r
    assert r["data"]["indicator"] == "banking_spi"
