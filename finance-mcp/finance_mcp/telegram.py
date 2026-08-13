"""Telegram Bot API client — thin async wrapper over httpx.

Exposed to Hermes/Claude via MCP tools in server.py. No background poller;
callers drive `getUpdates` themselves (long-poll or manual).
"""
from __future__ import annotations
import os
from typing import Any
import httpx

from .errors import FinanceError, ErrorCode

API_ROOT = "https://api.telegram.org"


def _token() -> str:
    tok = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not tok:
        raise FinanceError(
            ErrorCode.AUTHENTICATION_FAILED,
            "TELEGRAM_BOT_TOKEN not set",
            provider="telegram",
        )
    return tok


async def _call(method: str, payload: dict[str, Any] | None = None,
                timeout: float = 15.0) -> dict:
    url = f"{API_ROOT}/bot{_token()}/{method}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=payload or {})
    try:
        body = r.json()
    except Exception:
        raise FinanceError(
            ErrorCode.PROVIDER_UNAVAILABLE,
            f"telegram: non-json response ({r.status_code})",
            provider="telegram",
        )
    if not body.get("ok"):
        code = body.get("error_code")
        ec = ErrorCode.AUTHENTICATION_FAILED if code == 401 else ErrorCode.PROVIDER_UNAVAILABLE
        raise FinanceError(
            ec,
            f"telegram: {body.get('description', 'unknown error')}",
            provider="telegram",
            details={"error_code": code},
        )
    return body.get("result")


async def get_me() -> dict:
    return await _call("getMe")


async def send_message(chat_id: int | str, text: str,
                       parse_mode: str | None = None,
                       disable_web_page_preview: bool = True) -> dict:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": disable_web_page_preview,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return await _call("sendMessage", payload)


async def get_updates(offset: int | None = None, limit: int = 100,
                      timeout: int = 0) -> list[dict]:
    payload: dict[str, Any] = {"limit": limit, "timeout": timeout}
    if offset is not None:
        payload["offset"] = offset
    # long-poll: extend httpx timeout past bot API timeout
    return await _call("getUpdates", payload, timeout=max(30.0, timeout + 15))
