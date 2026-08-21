import logging

from finance_mcp.logging_ import kv, tool_call


def test_kv_redacts_secrets():
    s = kv(tool="get_quote", symbol="NVDA", api_key="deadbeef", token="xyz")
    assert "deadbeef" not in s and "xyz" not in s
    assert "api_key=***" in s and "token=***" in s
    assert "symbol=NVDA" in s


def test_kv_drops_none():
    s = kv(tool="get_quote", cache=None, symbol="NVDA")
    assert "cache" not in s


def test_tool_call_emits_success(caplog):
    with caplog.at_level(logging.INFO, logger="finance_mcp"):
        with tool_call("get_quote", symbol="NVDA", provider="yahoo") as ctx:
            ctx["hit"]()
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "tool=get_quote" in joined
    assert "cache=hit" in joined
    assert "symbol=NVDA" in joined
    assert "latency_ms=" in joined


def test_tool_call_emits_error(caplog):
    with caplog.at_level(logging.ERROR, logger="finance_mcp"):
        try:
            with tool_call("get_quote", symbol="BAD"):
                raise ValueError("boom")
        except ValueError:
            pass
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "error=ValueError" in joined
    assert "symbol=BAD" in joined
