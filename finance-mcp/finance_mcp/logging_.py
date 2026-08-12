"""Structured logging for MCP tool calls. Never logs API keys, credentials, or portfolio positions."""
from __future__ import annotations
import logging
import os
import sys
import time
from contextlib import contextmanager
from typing import Any

_LEVEL = os.getenv("FINANCE_LOG_LEVEL", "INFO").upper()

logger = logging.getLogger("finance_mcp")
if not logger.handlers:
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s finance_mcp %(message)s"))
    logger.addHandler(h)
logger.setLevel(_LEVEL)
# Propagate to root so downstream log aggregators / pytest caplog receive records.
logger.propagate = True


_REDACT_KEYS = {"api_key", "apikey", "token", "authorization", "password", "secret"}


def _redact(kv: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in kv.items():
        if k.lower() in _REDACT_KEYS:
            out[k] = "***"
        else:
            out[k] = v
    return out


def kv(**fields: Any) -> str:
    return " ".join(f"{k}={v}" for k, v in _redact(fields).items() if v is not None)


@contextmanager
def tool_call(tool: str, **fields: Any):
    """Emit start + end lines with latency_ms + cache + error status."""
    start = time.monotonic()
    ctx: dict[str, Any] = {"cache": "miss", "error": None}

    def mark_hit() -> None:
        ctx["cache"] = "hit"

    def mark_error(err: Any) -> None:
        ctx["error"] = err

    try:
        yield {"hit": mark_hit, "error": mark_error}
    except BaseException as e:
        ctx["error"] = type(e).__name__
        raise
    finally:
        latency_ms = int((time.monotonic() - start) * 1000)
        line = kv(tool=tool, latency_ms=latency_ms, cache=ctx["cache"],
                  error=ctx["error"], **fields)
        (logger.error if ctx["error"] else logger.info)(line)
