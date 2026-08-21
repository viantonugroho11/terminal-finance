"""Telegram outbound helper — env gate, truncation, HTTP outcome mapping.

Covers `finance_mcp.watch.telegram.send`, which never raises: it reports
delivery outcome as `(ok, error)` so the alert evaluator can keep running
when Telegram is unconfigured or down.
"""
from __future__ import annotations

import asyncio

import pytest
from finance_mcp.watch import telegram as tg


def _run(coro):
    return asyncio.run(coro)


class _FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


class _FakeClient:
    """Stands in for httpx.AsyncClient; records the single POST it receives."""

    def __init__(self, response=None, raises: Exception | None = None):
        self._response = response or _FakeResponse(200)
        self._raises = raises
        self.calls: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, url, json=None):
        self.calls.append((url, json or {}))
        if self._raises is not None:
            raise self._raises
        return self._response


@pytest.fixture
def patch_client(monkeypatch):
    """Install a fake AsyncClient and hand the instance back to the test."""

    def _install(client: _FakeClient) -> _FakeClient:
        monkeypatch.setattr(tg.httpx, "AsyncClient", lambda **kw: client)
        return client

    return _install


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)


def test_missing_token_is_noop(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    ok, err = _run(tg.send("hello"))
    assert ok is False
    assert err == "telegram env not configured"


def test_missing_chat_id_is_noop(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc123")
    ok, err = _run(tg.send("hello"))
    assert ok is False
    assert err == "telegram env not configured"


def test_explicit_chat_id_overrides_env(monkeypatch, patch_client):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "from-env")
    client = patch_client(_FakeClient())

    ok, err = _run(tg.send("hello", chat_id="explicit"))

    assert (ok, err) == (True, None)
    url, payload = client.calls[0]
    assert url == "https://api.telegram.org/botabc123/sendMessage"
    assert payload["chat_id"] == "explicit"
    assert payload["parse_mode"] == "Markdown"


def test_message_truncated_to_telegram_cap(monkeypatch, patch_client):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    client = patch_client(_FakeClient())

    ok, _ = _run(tg.send("x" * 5000))

    assert ok is True
    assert len(client.calls[0][1]["text"]) == 4096


def test_http_error_reported_not_raised(monkeypatch, patch_client):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    patch_client(_FakeClient(_FakeResponse(429, "Too Many Requests")))

    ok, err = _run(tg.send("hello"))

    assert ok is False
    assert err.startswith("telegram http 429:")


def test_transport_exception_reported_not_raised(monkeypatch, patch_client):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    patch_client(_FakeClient(raises=RuntimeError("connection reset")))

    ok, err = _run(tg.send("hello"))

    assert ok is False
    assert err == "telegram error: RuntimeError: connection reset"
