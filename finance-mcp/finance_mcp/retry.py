"""Bounded exponential backoff for transient provider errors."""
from __future__ import annotations
import asyncio
import random
from typing import Awaitable, Callable, TypeVar
from .errors import FinanceError, ErrorCode, classify

T = TypeVar("T")

_RETRYABLE = {
    ErrorCode.TIMEOUT,
    ErrorCode.PROVIDER_UNAVAILABLE,
    ErrorCode.RATE_LIMITED,
}


async def with_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 10.0,
    provider: str | None = None,
    symbol: str | None = None,
) -> T:
    last: FinanceError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except FinanceError as e:
            last = e
        except BaseException as e:  # includes asyncio.CancelledError → re-raise below
            if isinstance(e, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
            last = classify(e, provider=provider, symbol=symbol)

        if last.code not in _RETRYABLE or attempt == max_attempts:
            raise last

        if last.retry_after_seconds is not None:
            delay = min(float(last.retry_after_seconds), max_delay)
        else:
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
        # Jitter to spread retry storms
        delay += random.uniform(0, delay * 0.2)
        await asyncio.sleep(delay)

    assert last is not None
    raise last
