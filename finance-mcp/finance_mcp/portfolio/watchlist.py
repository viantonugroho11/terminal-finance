"""Watchlists — simple CRUD."""
from __future__ import annotations
from . import db


def create(name: str) -> int:
    with db.cursor() as cur:
        cur.execute("INSERT OR IGNORE INTO watchlists(name) VALUES(?)", (name,))
        cur.execute("SELECT id FROM watchlists WHERE name=?", (name,))
        return int(cur.fetchone()["id"])


def add(name: str, symbol: str) -> None:
    wid = create(name)
    with db.cursor() as cur:
        cur.execute("INSERT OR IGNORE INTO watchlist_items(watchlist_id,symbol) VALUES(?,?)",
                    (wid, symbol.upper()))


def remove(name: str, symbol: str) -> None:
    with db.cursor() as cur:
        cur.execute("""DELETE FROM watchlist_items
            WHERE symbol=? AND watchlist_id=(SELECT id FROM watchlists WHERE name=?)""",
            (symbol.upper(), name))


def list_all() -> dict[str, list[str]]:
    with db.cursor() as cur:
        cur.execute("""SELECT w.name, i.symbol FROM watchlists w
            LEFT JOIN watchlist_items i ON i.watchlist_id=w.id
            ORDER BY w.name, i.symbol""")
        out: dict[str, list[str]] = {}
        for r in cur.fetchall():
            out.setdefault(r["name"], [])
            if r["symbol"]:
                out[r["name"]].append(r["symbol"])
        return out


def items(name: str) -> list[str]:
    return list_all().get(name, [])
