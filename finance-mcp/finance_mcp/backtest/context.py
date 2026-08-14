"""Strategy runtime context — enforces no-look-ahead.

Given a full bar series + current index, exposes read-only slices that
CANNOT include bars after `current_index`. Attempting to fetch a future
bar raises LookAheadError. This is the ADR-0029 "no look-ahead" guard.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


class LookAheadError(RuntimeError):
    """Strategy tried to peek at a future bar."""


@dataclass
class Order:
    symbol: str
    side: str            # BUY | SELL
    qty: float
    type: str = "MKT"    # MKT | LMT
    limit_price: float | None = None


@dataclass
class Position:
    symbol: str
    qty: float = 0.0
    avg_price: float = 0.0


@dataclass
class BarContext:
    symbol: str
    _bars: list[dict[str, Any]]
    _index: int
    portfolio: dict[str, Position] = field(default_factory=dict)
    cash: float = 0.0

    @property
    def now(self) -> str:
        return str(self._bars[self._index].get("ts") or self._index)

    @property
    def bar(self) -> dict[str, Any]:
        return self._bars[self._index]

    def prices(self, lookback: int = 1) -> list[dict[str, Any]]:
        """Past + current bars, oldest first. `lookback` includes current."""
        if lookback <= 0:
            return []
        start = max(0, self._index - lookback + 1)
        return list(self._bars[start:self._index + 1])

    def future(self, offset: int = 1) -> None:
        raise LookAheadError(
            f"future({offset}) called at index {self._index}; "
            "backtest strategy may not peek forward."
        )

    def position(self, symbol: str) -> Position:
        return self.portfolio.get(symbol.upper(),
                                  Position(symbol=symbol.upper()))
