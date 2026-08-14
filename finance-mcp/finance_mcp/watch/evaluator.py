"""Watch evaluator loop.

Called by cron (or MCP tool `watch_evaluate_once`). One pass through
eligible rules; fires + records events; respects cooldown via store.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Callable, Awaitable

from .rules import Rule
from . import store, metrics, telegram


def _format_message(r: Rule, value: float) -> str:
    return (
        f"*Watch fired* — `{r.symbol}`\n"
        f"metric: `{r.metric}`  op: `{r.op}`  threshold: `{r.threshold}`\n"
        f"value: `{value:.4f}`\n"
        f"rule id: `{r.id}`"
    )


async def evaluate_rule(
    r: Rule,
    *,
    sender: Callable[[str, str | None], Awaitable[tuple[bool, str | None]]] = telegram.send,
) -> dict:
    value = await metrics.resolve(r.metric, r.symbol)
    if value is None:
        return {"id": r.id, "status": "skipped", "reason": "metric_unresolved"}
    if not metrics.compare(r.op, value, r.threshold):
        return {"id": r.id, "status": "no_trigger", "value": value}
    chat_id = None
    if r.channel.startswith("telegram:") and r.channel != "telegram:default":
        chat_id = r.channel.split(":", 1)[1]
    ok, err = await sender(_format_message(r, value), chat_id)
    store.record_fire(r.id, value, delivered=ok, error=err)
    return {"id": r.id, "status": "fired", "value": value,
            "delivered": ok, "error": err}


async def evaluate_once(
    sender: Callable[[str, str | None], Awaitable[tuple[bool, str | None]]] = telegram.send,
) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    results = []
    for r in list(store.eligible_now(now)):
        try:
            results.append(await evaluate_rule(r, sender=sender))
        except Exception as e:
            results.append({"id": r.id, "status": "error",
                            "error": f"{type(e).__name__}: {e}"})
    return results


def evaluate_once_sync(sender=telegram.send) -> list[dict]:
    return asyncio.run(evaluate_once(sender))
