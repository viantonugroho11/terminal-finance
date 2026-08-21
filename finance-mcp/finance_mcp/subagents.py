"""In-process subagent shim — bridges Phase F Steps 1–2 to Step 3.

Hermes' native subagent runtime (ADR-0015) is external and not yet
stable. Meanwhile the `equity-research` coordinator wants to describe
its plan in terms of sub-skills so the migration to real subagents
is a wiring swap, not a rewrite.

`SubagentRuntime` is a tiny in-process fan-out helper that:
  - accepts named specialist tasks (skill_name, kwargs)
  - runs their tool-call plans concurrently via asyncio
  - collects (name, result_or_error) tuples
  - carries a per-task time budget

It does NOT invoke an LLM. Each specialist task is a Python callable
that takes the shared router facade (registry.*) and returns
structured data — the coordinator interprets. This lets us prove the
composition + parallelism story with real code today, then swap the
runner for `hermes.spawn_subagent(...)` when that lands.

The evaluator loop (ADR-0016) plugs in the same way: coordinator's
final Markdown gets scored, verdict drives a bounded retry.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)


@dataclass
class SubagentTask:
    name: str                                    # e.g. "fundamental"
    fn: Callable[[], Awaitable[Any]]
    timeout_seconds: float = 30.0


@dataclass
class SubagentResult:
    name: str
    ok: bool
    value: Any = None
    error: str | None = None
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name, "ok": self.ok,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            **({"value": self.value} if self.ok else {"error": self.error}),
        }


@dataclass
class FanOutReport:
    results: list[SubagentResult] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    total_wall_clock_seconds: float = 0.0

    def by_name(self, name: str) -> SubagentResult | None:
        for r in self.results:
            if r.name == name:
                return r
        return None

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_wall_clock_seconds": round(self.total_wall_clock_seconds, 3),
            "results": [r.to_dict() for r in self.results],
        }


class SubagentRuntime:
    """Minimal fan-out. Swap for Hermes subagents when ADR-0015 lands."""

    def __init__(self, max_concurrency: int = 8):
        # asyncio.Semaphore binds to a loop on Python 3.9; create per-call
        # instead so importing the module never touches a loop.
        self._max_concurrency = max_concurrency

    async def _run_one(self, task: SubagentTask, sem: asyncio.Semaphore) -> SubagentResult:
        async with sem:
            t0 = time.monotonic()
            try:
                value = await asyncio.wait_for(task.fn(), timeout=task.timeout_seconds)
                return SubagentResult(name=task.name, ok=True, value=value,
                                      elapsed_seconds=time.monotonic() - t0)
            except asyncio.TimeoutError:
                return SubagentResult(name=task.name, ok=False,
                                      error=f"timeout after {task.timeout_seconds}s",
                                      elapsed_seconds=time.monotonic() - t0)
            except BaseException as e:
                if isinstance(e, (asyncio.CancelledError, KeyboardInterrupt,
                                  SystemExit)):
                    raise
                log.warning("subagent %s failed: %s", task.name, e)
                return SubagentResult(name=task.name, ok=False,
                                      error=f"{type(e).__name__}: {e}",
                                      elapsed_seconds=time.monotonic() - t0)

    async def fan_out(self, tasks: list[SubagentTask]) -> FanOutReport:
        from datetime import datetime, timezone
        started = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic()
        sem = asyncio.Semaphore(self._max_concurrency)
        results = await asyncio.gather(*(self._run_one(t, sem) for t in tasks))
        finished = datetime.now(timezone.utc).isoformat()
        return FanOutReport(
            results=list(results),
            started_at=started, finished_at=finished,
            total_wall_clock_seconds=time.monotonic() - t0,
        )


# Process-wide singleton so callers don't rebuild the semaphore.
runtime = SubagentRuntime()
