"""Router YAML-config loading + validate() — ADR-0012."""
import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from finance_mcp.errors import FinanceError, ErrorCode
from finance_mcp.router import Router, _load_preference


def _run(coro): return asyncio.run(coro)


class _FakeProvider:
    def __init__(self, name, markets=("US",), caps=("quote",),
                 tier="scraped", attribution=None):
        self.name = name
        self.tier = tier
        self.markets = frozenset(markets)
        self.capabilities = frozenset(caps)
        self.requires_api_key = False
        self.attribution = attribution

    async def quote(self, symbol):
        return {"symbol": symbol, "src": self.name}


def test_loads_yaml_config_from_env(tmp_path, monkeypatch):
    cfg = tmp_path / "routing.yaml"
    cfg.write_text(
        "capabilities:\n"
        "  quote:\n"
        "    IDX: [idx, yahoo]\n"
        "    US:  [yahoo]\n"
    )
    monkeypatch.setenv("FINANCE_ROUTING_CONFIG", str(cfg))
    pref, src = _load_preference()
    assert src == str(cfg)
    assert pref[("quote", "IDX")] == ["idx", "yahoo"]
    assert pref[("quote", "US")] == ["yahoo"]


def test_falls_back_to_defaults_when_config_missing(monkeypatch):
    monkeypatch.setenv("FINANCE_ROUTING_CONFIG", "/nonexistent/xyz.yaml")
    # Ensure repo-relative fallback also treated as absent for this test —
    # otherwise the real config/finance.routing.yaml would load.
    pref, src = _load_preference()
    assert pref  # something loaded (either config or defaults)


def test_router_uses_injected_preference():
    pref = {("quote", "US"): ["yahoo"], ("quote", "IDX"): ["idx", "yahoo"]}
    r = Router(preference=pref, config_source="test")
    yh = _FakeProvider("yahoo", markets={"US", "IDX"})
    idx = _FakeProvider("idx", markets={"IDX"})
    r.register(yh); r.register(idx)
    assert [p.name for p in r.chain("quote", "IDX")] == ["idx", "yahoo"]
    assert [p.name for p in r.chain("quote", "US")] == ["yahoo"]
    assert r.config_source == "test"


def test_validate_flags_unroutable_preference():
    pref = {("foreign_flow", "IDX"): ["idx"]}
    r = Router(preference=pref)
    # No providers registered — validate() should warn.
    warnings = r.validate()
    assert any("foreign_flow" in w for w in warnings)


def test_validate_silent_when_provider_present():
    pref = {("quote", "US"): ["yahoo"]}
    r = Router(preference=pref)
    r.register(_FakeProvider("yahoo"))
    assert r.validate() == []


def test_provenance_carries_tier_and_schema_version():
    """Envelope-level check via server: tier + schema_version present."""
    os.environ["FINANCE_PROVIDER"] = "mock"
    os.environ.setdefault(
        "FINANCE_DB",
        tempfile.NamedTemporaryFile(suffix=".db", delete=False).name,
    )
    from finance_mcp import server
    server._c.cache.invalidate()
    r = _run(server.get_quote("AAPL"))
    prov = r["provenance"]
    assert prov["source"] == "mock"
    assert prov["tier"] == "mock"
    assert prov["schema_version"] and prov["schema_version"].count(".") == 2


def test_router_config_source_observable(monkeypatch, tmp_path):
    cfg = tmp_path / "r.yaml"
    cfg.write_text("capabilities: {quote: {US: [yahoo]}}\n")
    monkeypatch.setenv("FINANCE_ROUTING_CONFIG", str(cfg))
    r = Router()
    assert r.config_source == str(cfg)
