"""BiProvider — mocked HTTP."""
import asyncio

import httpx
import pytest
from finance_mcp.errors import ErrorCode, FinanceError
from finance_mcp.providers.bi import BiProvider


def _client(handler):
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://www.bi.go.id",
    )


def _run(coro): return asyncio.run(coro)


_BI_RATE_HTML = """
<table>
  <tr><th>Tanggal</th><th>BI-Rate</th></tr>
  <tr><td>22 Juli 2026</td><td>5,75%</td></tr>
  <tr><td>18 Juni 2026</td><td>6,00%</td></tr>
  <tr><td>21 Mei 2026</td><td>6,00%</td></tr>
</table>
"""

_JISDOR_HTML = """
<table>
  <tr><th>Tanggal</th><th>Kurs</th></tr>
  <tr><td>13 Agustus 2026</td><td>17.882,00</td></tr>
  <tr><td>12 Agustus 2026</td><td>17.875,50</td></tr>
</table>
"""


def test_bi_rate_parses():
    def handler(req):
        assert "bi-rate" in req.url.path
        return httpx.Response(200, text=_BI_RATE_HTML,
                              headers={"Content-Type": "text/html"})
    p = BiProvider(http=_client(handler))
    s = _run(p.macro_indicator("bi_rate"))
    assert s.indicator == "bi_rate"
    assert s.source == "bi"
    assert s.unit == "%"
    assert len(s.observations) == 3
    # Sorted ascending.
    assert s.observations[-1].period == "2026-07-22"
    assert s.observations[-1].value == 5.75
    assert s.attribution == "Bank Indonesia"


def test_jisdor_parses_and_supports_alias():
    def handler(req):
        assert "jisdor" in req.url.path
        return httpx.Response(200, text=_JISDOR_HTML,
                              headers={"Content-Type": "text/html"})
    p = BiProvider(http=_client(handler))
    s1 = _run(p.macro_indicator("jisdor"))
    assert s1.observations[-1].value == 17882.00
    assert s1.observations[-1].period == "2026-08-13"
    s2 = _run(p.macro_indicator("fx_usd_idr"))
    assert s2.indicator == "jisdor"


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


def test_unparseable_html_raises_data_unavailable():
    def handler(req):
        return httpx.Response(200, text="<html>no table here</html>",
                              headers={"Content-Type": "text/html"})
    p = BiProvider(http=_client(handler))
    with pytest.raises(FinanceError) as ei:
        _run(p.macro_indicator("bi_rate"))
    assert ei.value.code == ErrorCode.DATA_UNAVAILABLE


def test_bi_provider_declarations():
    p = BiProvider(http=_client(lambda r: httpx.Response(200, json={})))
    assert p.name == "bi" and p.tier == "primary"
    assert p.markets == frozenset({"MACRO"})
    assert "macro:bi_rate" in p.capabilities
    assert "macro:jisdor" in p.capabilities
