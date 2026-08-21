"""OjkProvider — reads local JSON snapshot."""
import asyncio
import json
import tempfile
from pathlib import Path

import pytest
from finance_mcp.errors import ErrorCode, FinanceError
from finance_mcp.providers.ojk import OjkProvider


def _run(coro): return asyncio.run(coro)


def _snapshot(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_no_snapshot_raises_data_unavailable():
    p = OjkProvider(snapshot_path=None)
    with pytest.raises(FinanceError) as ei:
        _run(p.macro_indicator("npl"))
    assert ei.value.code == ErrorCode.DATA_UNAVAILABLE


def test_unknown_indicator_raises_data_unavailable():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        Path(f.name).write_text("{}", encoding="utf-8")
        p = OjkProvider(snapshot_path=f.name)
    with pytest.raises(FinanceError) as ei:
        _run(p.macro_indicator("bi_rate"))
    assert ei.value.code == ErrorCode.DATA_UNAVAILABLE


def test_npl_series_parses():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    _snapshot(path, {
        "_meta": {"frequency": "monthly"},
        "npl": [
            {"period": "2025-06", "value": 2.31, "unit": "%"},
            {"period": "2025-07", "value": 2.28, "unit": "%"},
        ],
    })
    p = OjkProvider(snapshot_path=path)
    s = _run(p.macro_indicator("npl"))
    assert s.indicator == "npl"
    assert s.source == "ojk"
    assert s.unit == "%"
    assert len(s.observations) == 2
    assert s.observations[0].period == "2025-06"


def test_empty_series_raises():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    _snapshot(path, {"npl": []})
    p = OjkProvider(snapshot_path=path)
    with pytest.raises(FinanceError) as ei:
        _run(p.macro_indicator("npl"))
    assert ei.value.code == ErrorCode.DATA_UNAVAILABLE
