"""End-to-end market-aware routing.

Runs under FINANCE_PROVIDER=mock so no network. Verifies that:
  - existing US flow keeps working
  - new IDX tools reach the mock provider through the router
  - provenance now carries the resolver block
  - new tools (dividends, corporate actions, sector) return sensible data
"""
import asyncio
import os
import tempfile

os.environ["FINANCE_PROVIDER"] = "mock"
os.environ.setdefault("FINANCE_DB",
                      tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)

from finance_mcp import server  # noqa: E402


def _run(coro): return asyncio.run(coro)


def _payload(reply):
    assert "error" not in reply, reply
    return reply["data"], reply["provenance"]


def test_us_quote_still_works():
    d, prov = _payload(_run(server.get_quote("AAPL")))
    assert d["symbol"] == "AAPL"
    assert prov["source"] == "mock"
    # Resolver present on any symbol call.
    assert prov["resolver"]["market"] == "US"
    assert prov["resolver"]["canonical_symbol"] == "AAPL"


def test_idx_symbol_routes_and_reports_resolver():
    server._c.cache.invalidate()
    d, prov = _payload(_run(server.get_quote("BBCA")))
    assert prov["resolver"]["market"] == "IDX"
    assert prov["resolver"]["canonical_symbol"] == "BBCA.JK"
    assert prov["resolver"]["source"] == "allowlist"


def test_idx_suffix_symbol_also_routes():
    server._c.cache.invalidate()
    _, prov = _payload(_run(server.get_quote("TLKM.JK")))
    assert prov["resolver"]["market"] == "IDX"
    assert prov["resolver"]["source"] == "suffix"


def test_new_dividends_tool_returns_events():
    d, prov = _payload(_run(server.get_dividends("BBCA")))
    assert d["symbol"] == "BBCA"
    assert isinstance(d["events"], list) and d["events"]
    assert prov["resolver"]["market"] == "IDX"


def test_new_corporate_actions_tool():
    d, _ = _payload(_run(server.get_corporate_actions("BBRI")))
    assert d["symbol"] == "BBRI"
    assert d["events"][0]["kind"] == "split"


def test_new_sector_info_tool():
    d, _ = _payload(_run(server.get_sector_info("BMRI")))
    assert d["symbol"] == "BMRI"
    assert d["sector_name"] == "Technology"  # mock returns generic sector


def test_resolve_symbol_tool():
    r = _run(server.resolve_symbol_tool("BBCA"))
    assert r["resolved"]["market"] == "IDX"
    assert r["resolved"]["canonical_symbol"] == "BBCA.JK"


def test_cache_hit_on_second_idx_quote():
    server._c.cache.invalidate()
    r1 = _run(server.get_quote("ASII"))
    r2 = _run(server.get_quote("ASII"))
    assert r1["provenance"]["cache_hit"] is False
    assert r2["provenance"]["cache_hit"] is True
    # Provenance still shows the same resolver on the cached reply.
    assert r2["provenance"]["resolver"]["market"] == "IDX"


def test_cache_stats_lists_providers():
    st = _run(server.cache_stats())
    assert "providers" in st
    names = {p["name"] for p in st["providers"]}
    assert "mock" in names


def test_us_and_idx_do_not_collide_in_cache():
    """Cache key includes market; a US ticker that shares no code with any
    IDX allowlist entry must still be independent."""
    server._c.cache.invalidate()
    _run(server.get_quote("AAPL"))
    _run(server.get_quote("BBCA"))
    st = _run(server.cache_stats())
    assert st["cache"]["size"] >= 2
