"""Telegram outbound helper. Uses TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID.

Hermes has its own gateway; this fallback lets the evaluator run outside
Hermes (cron in the finance-mcp container). Silent no-op if env unset —
returned bool tells the caller delivery outcome.
"""
from __future__ import annotations
import os
import httpx


async def send(text: str, chat_id: str | None = None) -> tuple[bool, str | None]:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False, "telegram env not configured"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json={
                "chat_id": chat, "text": text[:4096],
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            })
        if r.status_code == 200:
            return True, None
        return False, f"telegram http {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, f"telegram error: {type(e).__name__}: {e}"
