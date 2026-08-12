"""BpsProvider — mocked HTTP + API key gate."""
import asyncio
import httpx
import pytest

from finance_mcp.errors import FinanceError, ErrorCode
from finance_mcp.providers.bps import BpsProvider


def _client(handler):
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://webapi.bps.go.id",
    )


def _run(coro): return asyncio.run(coro)


def test_missing_key_raises_auth_failed():
    p = BpsProvider(http=_client(lambda r: httpx.Response(200, json={})),
                    api_key="")
    with pytest.raises(FinanceError) as ei:
        _run(p.macro_indicator("inflation"))
    assert ei.value.code == ErrorCode.AUTHENTICATION_FAILED


def test_401_from_bps_maps_auth_failed():
    def handler(req):
        assert "/var/1905/key/testkey" in req.url.path
        return httpx.Response(401)
    p = BpsProvider(http=_client(handler), api_key="testkey")
    with pytest.raises(FinanceError) as ei:
        _run(p.macro_indicator("inflation"))
    assert ei.value.code == ErrorCode.AUTHENTICATION_FAILED


def test_unknown_indicator_raises_data_unavailable():
    p = BpsProvider(http=_client(lambda r: httpx.Response(200, json={})),
                    api_key="k")
    with pytest.raises(FinanceError) as ei:
        _run(p.macro_indicator("bi_rate"))
    assert ei.value.code == ErrorCode.DATA_UNAVAILABLE


def test_inflation_parses_shape():
    def handler(req):
        return httpx.Response(200, json={
            "datacontent": {"1905117": "2.10", "1905118": "2.05"},
            "tahun":       [{"val": "117", "label": "2024"},
                            {"val": "118", "label": "2025"}],
            "turtahun":    [],
        })
    p = BpsProvider(http=_client(handler), api_key="k")
    s = _run(p.macro_indicator("inflation"))
    assert s.indicator == "inflation"
    assert s.source == "bps"
    assert s.unit == "%"
    assert len(s.observations) == 2
    assert s.observations[0].value in (2.10, 2.05)


def test_empty_datacontent_raises_data_unavailable():
    def handler(req):
        return httpx.Response(200, json={"datacontent": {}})
    p = BpsProvider(http=_client(handler), api_key="k")
    with pytest.raises(FinanceError) as ei:
        _run(p.macro_indicator("gdp"))
    assert ei.value.code == ErrorCode.DATA_UNAVAILABLE
