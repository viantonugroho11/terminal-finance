"""Structured errors surfaced to Hermes via MCP.

Never swallow errors. Never substitute fake defaults. Every failure returns a
FinanceError with a stable code so skills can react (retry, back off, apologize).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    SYMBOL_NOT_FOUND       = "SYMBOL_NOT_FOUND"
    INVALID_SYMBOL         = "INVALID_SYMBOL"
    PROVIDER_UNAVAILABLE   = "PROVIDER_UNAVAILABLE"
    RATE_LIMITED           = "RATE_LIMITED"
    AUTHENTICATION_FAILED  = "AUTHENTICATION_FAILED"
    DATA_UNAVAILABLE       = "DATA_UNAVAILABLE"
    TIMEOUT                = "TIMEOUT"
    INTERNAL               = "INTERNAL"
    # Screener (ADR-0025): the caller asked to filter or sort on a field that
    # is not in the allowlist. Distinct from DATA_UNAVAILABLE because the
    # request itself is wrong, not the data.
    SCREENER_FIELD_UNKNOWN = "SCREENER_FIELD_UNKNOWN"


@dataclass
class FinanceError(Exception):
    code: ErrorCode
    message: str
    provider: str | None = None
    symbol: str | None = None
    retry_after_seconds: int | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        parts = [f"[{self.code.value}] {self.message}"]
        if self.provider: parts.append(f"provider={self.provider}")
        if self.symbol:   parts.append(f"symbol={self.symbol}")
        if self.retry_after_seconds is not None:
            parts.append(f"retry_after={self.retry_after_seconds}s")
        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["code"] = self.code.value
        return {"error": {k: v for k, v in d.items() if v not in (None, {}, [])}}


def classify(exc: BaseException, *, provider: str | None = None,
             symbol: str | None = None) -> FinanceError:
    """Map an arbitrary exception into a FinanceError with a best-effort code."""
    if isinstance(exc, FinanceError):
        return exc
    name = type(exc).__name__.lower()
    msg = str(exc) or name
    lower = msg.lower()

    if ("rate" in lower and "limit" in lower) or "429" in msg or "too many requests" in lower:
        return FinanceError(ErrorCode.RATE_LIMITED, msg, provider, symbol)
    if "timeout" in name or "timedout" in name or "timeout" in lower:
        return FinanceError(ErrorCode.TIMEOUT, msg, provider, symbol)
    if "unauthor" in lower or "forbidden" in lower or "401" in msg or "403" in msg:
        return FinanceError(ErrorCode.AUTHENTICATION_FAILED, msg, provider, symbol)
    if "notfound" in name or "404" in msg or "no data" in lower:
        return FinanceError(ErrorCode.SYMBOL_NOT_FOUND, msg, provider, symbol)
    if "connection" in lower or "unreachable" in lower or "502" in msg or "503" in msg:
        return FinanceError(ErrorCode.PROVIDER_UNAVAILABLE, msg, provider, symbol)
    return FinanceError(ErrorCode.INTERNAL, msg, provider, symbol)
