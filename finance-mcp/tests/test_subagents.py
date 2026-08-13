"""SubagentRuntime fan-out shim (Phase F bridge)."""
import asyncio
import time
import pytest

from finance_mcp.subagents import (
    SubagentRuntime, SubagentTask, SubagentResult, FanOutReport,
)


def _run(coro): return asyncio.run(coro)


def test_fanout_runs_concurrently():
    async def slow(v):
        await asyncio.sleep(0.05)
        return v

    tasks = [SubagentTask(name=f"t{i}", fn=lambda i=i: slow(i)) for i in range(4)]
    rt = SubagentRuntime(max_concurrency=4)
    rep = _run(rt.fan_out(tasks))
    assert len(rep.results) == 4
    # 4x 50ms serial = 200ms; concurrent = ~50ms. Give slack.
    assert rep.total_wall_clock_seconds < 0.18
    assert all(r.ok for r in rep.results)


def test_fanout_captures_failure_without_killing_batch():
    async def ok(): return "yay"
    async def boom(): raise RuntimeError("nope")
    tasks = [
        SubagentTask("a", ok),
        SubagentTask("b", boom),
        SubagentTask("c", ok),
    ]
    rt = SubagentRuntime()
    rep = _run(rt.fan_out(tasks))
    assert [r.ok for r in rep.results] == [True, False, True]
    b = rep.by_name("b")
    assert b is not None
    assert "RuntimeError" in b.error


def test_fanout_honors_task_timeout():
    async def slow(): await asyncio.sleep(1.0)
    tasks = [SubagentTask("s", slow, timeout_seconds=0.05)]
    rep = _run(SubagentRuntime().fan_out(tasks))
    assert rep.results[0].ok is False
    assert "timeout" in rep.results[0].error


def test_report_serializes():
    async def ok(): return {"symbol": "X", "value": 42}
    rep = _run(SubagentRuntime().fan_out([SubagentTask("t", ok)]))
    d = rep.to_dict()
    assert set(d) == {"started_at", "finished_at",
                      "total_wall_clock_seconds", "results"}
    assert d["results"][0]["value"]["symbol"] == "X"


def test_max_concurrency_serializes_beyond_limit():
    active = 0
    peak = 0

    async def track():
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        active -= 1

    tasks = [SubagentTask(f"t{i}", track) for i in range(8)]
    rt = SubagentRuntime(max_concurrency=2)
    _run(rt.fan_out(tasks))
    assert peak <= 2
