"""Watch rule model + validation.

Metric allowlist matches ADR-0023 + sentiment_spike from ADR-0028.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from .. import tenant

METRICS = {
    "price_change_pct_intraday",
    "price_change_pct_1d",
    "price_change_pct_5d",
    "price_change_pct_20d",
    "volume_vs_ma20",
    "foreign_net_flow_idr",
    "bi_rate_change_bps",
    "sentiment_spike",
}

OPS = {">", "<", ">=", "<=", "=="}

_MACRO_PREFIX = "macro_release:"


def is_valid_metric(metric: str) -> bool:
    if metric in METRICS:
        return True
    return metric.startswith(_MACRO_PREFIX) and len(metric) > len(_MACRO_PREFIX)


@dataclass
class Rule:
    symbol: str
    metric: str
    op: str
    threshold: float
    id: str = field(default_factory=lambda: f"w_{uuid.uuid4().hex[:16]}")
    tenant_id: str = field(default_factory=lambda: tenant.current())
    window: str | None = None
    channel: str = "telegram:default"
    cooldown_sec: int = 3600
    last_fired_at: str | None = None
    disabled: bool = False
    note: str | None = None

    def __post_init__(self) -> None:
        self.symbol = self.symbol.upper()
        if self.op not in OPS:
            raise ValueError(f"invalid op: {self.op!r}")
        if not is_valid_metric(self.metric):
            raise ValueError(f"invalid metric: {self.metric!r}")
        self.threshold = float(self.threshold)

    def to_row(self) -> dict[str, Any]:
        d = asdict(self)
        d["disabled"] = 1 if self.disabled else 0
        return d

    @classmethod
    def from_row(cls, row: Any) -> Rule:
        return cls(
            id=row["id"],
            tenant_id=row["tenant_id"],
            symbol=row["symbol"],
            metric=row["metric"],
            op=row["op"],
            threshold=row["threshold"],
            window=row["window"],
            channel=row["channel"],
            cooldown_sec=row["cooldown_sec"],
            last_fired_at=row["last_fired_at"],
            disabled=bool(row["disabled"]),
            note=row["note"],
        )


_NL_HINTS = {
    "turun": ("price_change_pct_intraday", "<"),
    "drop": ("price_change_pct_intraday", "<"),
    "naik": ("price_change_pct_intraday", ">"),
    "up": ("price_change_pct_intraday", ">"),
    "volume": ("volume_vs_ma20", ">"),
    "asing": ("foreign_net_flow_idr", ">"),
    "sentimen": ("sentiment_spike", ">"),
    "sentiment": ("sentiment_spike", ">"),
    "bi rate": ("bi_rate_change_bps", "!="),
}

_PCT = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*%")
_MULT = re.compile(r"(\d+(?:\.\d+)?)\s*x")
_TICKER = re.compile(r"\b([A-Z]{2,5})\b")
_STOPWORDS = {
    "KALAU", "JIKA", "KETIKA", "SAAT", "APABILA",
    "IF", "WHEN", "THE", "AND", "OR", "ALERT", "ME",
    "WATCH", "PANTAU", "KABARI", "NOTIFY", "TURUN",
    "NAIK", "DROP", "UP", "DOWN", "VOLUME", "ASING",
    "RATE", "BI", "MACRO", "SENTIMEN", "SENTIMENT",
}


def parse_nl(text: str) -> Rule:
    """Best-effort NL → Rule; skill layer echoes for user confirmation.

    Deterministic heuristic — no LLM here. Skill can override any field.
    """
    t = text.lower()
    symbol = None
    for m in _TICKER.finditer(text.upper()):
        cand = m.group(1)
        if cand not in _STOPWORDS:
            symbol = cand
            break
    if symbol is None:
        raise ValueError("no ticker symbol found in text")

    metric = "price_change_pct_intraday"
    op = "<"
    for kw, (m, o) in _NL_HINTS.items():
        if kw in t:
            metric, op = m, o
            break

    threshold: float
    if metric == "volume_vs_ma20":
        m = _MULT.search(t)
        threshold = float(m.group(1)) if m else 2.0
    else:
        m = _PCT.search(t)
        threshold = float(m.group(1)) if m else -2.0
        if metric == "price_change_pct_intraday" and op == "<" and threshold > 0:
            threshold = -threshold

    return Rule(symbol=symbol, metric=metric, op=op, threshold=threshold)
