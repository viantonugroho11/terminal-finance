from finance_mcp.errors import FinanceError, ErrorCode, classify


def test_finance_error_str_and_dict():
    e = FinanceError(ErrorCode.RATE_LIMITED, "slow down", provider="yahoo",
                     symbol="NVDA", retry_after_seconds=30)
    s = str(e)
    assert "RATE_LIMITED" in s and "yahoo" in s and "NVDA" in s and "30s" in s
    d = e.to_dict()
    assert d["error"]["code"] == "RATE_LIMITED"
    assert d["error"]["retry_after_seconds"] == 30


def test_classify_rate_limit():
    e = classify(Exception("HTTP 429 Rate limit exceeded"), provider="yahoo")
    assert e.code == ErrorCode.RATE_LIMITED
    assert e.provider == "yahoo"


def test_classify_timeout_by_name():
    class TimeoutError(Exception): ...
    e = classify(TimeoutError("boom"))
    assert e.code == ErrorCode.TIMEOUT


def test_classify_auth():
    assert classify(Exception("401 Unauthorized")).code == ErrorCode.AUTHENTICATION_FAILED
    assert classify(Exception("403 Forbidden")).code == ErrorCode.AUTHENTICATION_FAILED


def test_classify_not_found():
    assert classify(Exception("404 not found")).code == ErrorCode.SYMBOL_NOT_FOUND
    assert classify(Exception("No data for XYZ")).code == ErrorCode.SYMBOL_NOT_FOUND


def test_classify_passthrough():
    orig = FinanceError(ErrorCode.INVALID_SYMBOL, "bad")
    assert classify(orig) is orig


def test_classify_fallback_internal():
    assert classify(ValueError("weird")).code == ErrorCode.INTERNAL
