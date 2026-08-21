"""Watch store — SQLite-backed CRUD + JSONL audit trail.

Spec calls for JSONL but shared finance.db is already the operational
store. JSONL kept as append-only audit sidecar at
`$FINANCE_DB_DIR/watches.audit.jsonl`.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from .. import tenant
from ..portfolio.db import connect, db_path
from .rules import Rule


def _audit_path() -> Path:
    return db_path().parent / "watches.audit.jsonl"


def _audit(kind: str, payload: dict) -> None:
    line = json.dumps(
        {"kind": kind, "at": datetime.now(timezone.utc).isoformat(),
         "payload": payload},
        separators=(",", ":"),
    )
    p = _audit_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def add(rule: Rule) -> Rule:
    row = rule.to_row()
    cols = ",".join(row.keys())
    placeholders = ",".join(f":{k}" for k in row.keys())
    with connect() as conn:
        conn.execute(f"INSERT INTO watches({cols}) VALUES({placeholders})", row)
    _audit("add", row)
    return rule


def get(watch_id: str) -> Rule | None:
    with connect() as conn:
        r = conn.execute("SELECT * FROM watches WHERE id=?", (watch_id,)).fetchone()
    return Rule.from_row(r) if r else None


def list_all(active_only: bool = False, tenant_id: str | None = None) -> list[Rule]:
    q = "SELECT * FROM watches WHERE tenant_id=?"
    args: tuple = (tenant_id or tenant.current(),)
    if active_only:
        q += " AND disabled=0"
    q += " ORDER BY created_at DESC"
    with connect() as conn:
        rows = conn.execute(q, args).fetchall()
    return [Rule.from_row(r) for r in rows]


def set_disabled(watch_id: str, disabled: bool) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE watches SET disabled=? WHERE id=?",
            (1 if disabled else 0, watch_id),
        )
    _audit("disabled" if disabled else "enabled", {"id": watch_id})
    return cur.rowcount > 0


def delete(watch_id: str) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM watches WHERE id=?", (watch_id,))
    _audit("delete", {"id": watch_id})
    return cur.rowcount > 0


def record_fire(watch_id: str, metric_value: float,
                delivered: bool, error: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        conn.execute(
            "INSERT INTO watch_events(watch_id, fired_at, metric_value, "
            "delivered, error) VALUES(?,?,?,?,?)",
            (watch_id, now, metric_value, 1 if delivered else 0, error),
        )
        conn.execute(
            "UPDATE watches SET last_fired_at=? WHERE id=?", (now, watch_id),
        )
    _audit("fire", {"id": watch_id, "value": metric_value,
                    "delivered": delivered, "error": error})


def eligible_now(now_iso: str) -> Iterable[Rule]:
    """Rules that are active and past their cooldown window."""
    for r in list_all(active_only=True):
        if r.last_fired_at is None:
            yield r
            continue
        try:
            last = datetime.fromisoformat(r.last_fired_at)
            now = datetime.fromisoformat(now_iso)
        except ValueError:
            yield r
            continue
        if (now - last).total_seconds() >= r.cooldown_sec:
            yield r
