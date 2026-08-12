import asyncio
import pytest
from finance_mcp.retry import with_retry
from finance_mcp.errors import FinanceError, ErrorCode


def _run(coro):
    return asyncio.run(coro)


def test_success_first_try():
    calls = 0

    async def ok():
        nonlocal calls
        calls += 1
        return "ok"

    assert _run(with_retry(ok)) == "ok"
    assert calls == 1


def test_retries_transient_then_succeeds():
    calls = 0

    async def flaky():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise FinanceError(ErrorCode.TIMEOUT, "boom")
        return "ok"

    assert _run(with_retry(flaky, max_attempts=5, base_delay=0.001)) == "ok"
    assert calls == 3


def test_no_retry_on_nonretryable():
    calls = 0

    async def bad():
        nonlocal calls
        calls += 1
        raise FinanceError(ErrorCode.INVALID_SYMBOL, "nope")

    with pytest.raises(FinanceError) as ei:
        _run(with_retry(bad, max_attempts=3, base_delay=0.001))
    assert ei.value.code == ErrorCode.INVALID_SYMBOL
    assert calls == 1


def test_exhausts_attempts():
    calls = 0

    async def dead():
        nonlocal calls
        calls += 1
        raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE, "down")

    with pytest.raises(FinanceError):
        _run(with_retry(dead, max_attempts=3, base_delay=0.001))
    assert calls == 3


def test_wraps_raw_exception():
    async def raw():
        raise Exception("HTTP 429")

    with pytest.raises(FinanceError) as ei:
        _run(with_retry(raw, max_attempts=2, base_delay=0.001))
    assert ei.value.code == ErrorCode.RATE_LIMITED
