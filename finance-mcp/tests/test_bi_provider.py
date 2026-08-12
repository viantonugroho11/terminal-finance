"""BiProvider — mocked HTTP."""
import asyncio
import httpx
import pytest

from finance_mcp.errors import FinanceError, ErrorCode
from finance_mcp.providers.bi import BiProvider


def _client(handler):
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://www.bi.go.id",
    )


def _run(coro): return asyncio.run(coro)


def test_bi_rate_parses():
    def handler(req):
        assert "getBIRateHistory" in req.url.path
        return httpx.Response(200, json={"data": [
            {"EffectiveDate": "2025-08-15", "Rate": "6.00"},
            {"EffectiveDate": "2025-07-15", "Rate": "6.25"},
        ]})
    p = BiProvider(http=_client(handler))
    s = _run(p.macro_indicator("bi_rate"))
    assert s.indicator == "bi_rate"
    assert s.source == "bi"
    assert s.unit == "%"
    assert len(s.observations) == 2
    assert s.observations[0].value == 6.00
    assert s.attribution == "Bank Indonesia"


def test_jisdor_parses_and_supports_alias():
    def handler(req):
        assert "getJisdorHistory" in req.url.path
        return httpx.Response(200, json={"data": [
            {"Date": "2025-08-13", "Kurs": "16123.50"},
        ]})
    p = BiProvider(http=_client(handler))
    s1 = _run(p.macro_indicator("jisdor"))
    assert s1.observations[0].value == 16123.50
    s2 = _run(p.macro_indicator("fx_usd_idr"))
    assert s2.indicator == "jisdor"  # alias normalized


def test_unknown_indicator_raises_data_unavailable():
    p = BiProvider(http=_client(lambda r: httpx.Response(200, json={})))
    with pytest.raises(FinanceError) as ei:
        _run(p.macro_indicator("gdp"))
    assert ei.value.code == ErrorCode.DATA_UNAVAILABLE


def test_bi_403_maps_provider_unavailable():
    def handler(req): return httpx.Response(403, text="blocked")
    p = BiProvider(http=_client(handler))
    with pytest.raises(FinanceError) as ei:
        _run(p.macro_indicator("bi_rate"))
    assert ei.value.code == ErrorCode.PROVIDER_UNAVAILABLE


def test_bi_provider_declarations():
    p = BiProvider(http=_client(lambda r: httpx.Response(200, json={})))
    assert p.name == "bi" and p.tier == "primary"
    assert p.markets == frozenset({"MACRO"})
    assert "macro:bi_rate" in p.capabilities
    assert "macro:jisdor" in p.capabilities
