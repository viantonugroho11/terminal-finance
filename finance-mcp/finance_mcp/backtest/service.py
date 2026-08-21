"""Backtest job store + runner. Sync v1 — no async worker pool.

Long-running jobs block the caller. When bar counts push runtimes past
a few seconds, move `_execute` onto a background thread + poll via
`get_status`; store schema already supports async transitions.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from ..portfolio.db import connect
from . import engine, strategies


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(*, strategy: str, params: dict[str, Any],
               universe: list[str], start: str, end: str,
               market: str = "ID") -> str:
    job_id = f"bt_{uuid.uuid4().hex[:16]}"
    with connect() as conn:
        conn.execute(
            "INSERT INTO backtest_jobs(id, strategy, params_json, "
            "universe_json, start_date, end_date, market, status) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (job_id, strategy, json.dumps(params),
             json.dumps(universe), start, end, market, "queued"),
        )
    return job_id


def _set_status(job_id: str, status: str, *, result: dict | None = None,
                error: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE backtest_jobs SET status=?, result_json=?, error=?, "
            "completed_at=? WHERE id=?",
            (status, json.dumps(result) if result is not None else None,
             error,
             _now() if status in ("done", "error") else None,
             job_id),
        )


def _load(job_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        r = conn.execute("SELECT * FROM backtest_jobs WHERE id=?",
                         (job_id,)).fetchone()
    return dict(r) if r else None


def execute(*, job_id: str, bars_by_symbol: dict[str, list[dict]]) -> dict:
    """Run a queued job. Caller supplies OHLCV (keeps engine offline)."""
    row = _load(job_id)
    if row is None:
        raise KeyError(f"unknown job: {job_id}")
    _set_status(job_id, "running")
    try:
        strategy_name = row["strategy"]
        fn = strategies.get(strategy_name)
        params = json.loads(row["params_json"] or "{}")
        universe = json.loads(row["universe_json"] or "[]")
        if not universe:
            raise ValueError("empty universe")
        # v1: single-symbol only. Multi-symbol composition = separate ADR.
        symbol = universe[0]
        bars = bars_by_symbol.get(symbol)
        if not bars:
            raise ValueError(f"no bars provided for {symbol}")
        result = engine.run(
            symbol=symbol, bars=bars, strategy_fn=fn,
            params=params, market=row["market"],
        )
        _set_status(job_id, "done", result=result)
        return result
    except Exception as e:
        _set_status(job_id, "error", error=f"{type(e).__name__}: {e}")
        raise


def get_status(job_id: str) -> dict[str, Any]:
    row = _load(job_id)
    if row is None:
        return {"error": {"code": "SYMBOL_NOT_FOUND",
                          "message": f"unknown job: {job_id}"}}
    return {"id": row["id"], "status": row["status"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"], "error": row["error"]}


def get_result(job_id: str) -> dict[str, Any]:
    row = _load(job_id)
    if row is None:
        return {"error": {"code": "SYMBOL_NOT_FOUND",
                          "message": f"unknown job: {job_id}"}}
    if row["status"] != "done":
        return {"id": row["id"], "status": row["status"],
                "error": row["error"], "result": None}
    return {"id": row["id"], "status": "done",
            "result": json.loads(row["result_json"] or "{}")}
