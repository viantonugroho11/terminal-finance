"""Telegram gateway — token gate + error mapping."""
import asyncio
import os

import pytest

from finance_mcp import telegram as tg
from finance_mcp.errors import FinanceError, ErrorCode


def _run(coro): return asyncio.run(coro)


def test_missing_token_raises_auth_failed(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with pytest.raises(FinanceError) as ei:
        tg._token()
    assert ei.value.code == ErrorCode.AUTHENTICATION_FAILED


def test_token_stripped(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "  abc123  ")
    assert tg._token() == "abc123"


def test_get_me_no_token_returns_auth_failed(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with pytest.raises(FinanceError) as ei:
        _run(tg.get_me())
    assert ei.value.code == ErrorCode.AUTHENTICATION_FAILED
