"""Background sweeps must cross tenants; interactive listing must not.

The failure this guards against is silent: a second tenant adds a watch, the
cron evaluator only ever looks at the process tenant, and the alert simply
never arrives. Nothing errors.
"""
from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

os.environ.setdefault(
    "FINANCE_DB", tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
)

from finance_mcp import migrations  # noqa: E402
from finance_mcp.portfolio import db as pdb  # noqa: E402
from finance_mcp.watch import db as wdb  # noqa: E402
from finance_mcp.watch import evaluator, store  # noqa: E402
from finance_mcp.watch.rules import Rule  # noqa: E402


@pytest.fixture
def two_tenants(monkeypatch, tmp_path):
    """One watch owned by 'local', one by 'tg_42'."""
    monkeypatch.setenv("FINANCE_DB", str(tmp_path / "mt.db"))
    pdb.init(); wdb.init(); migrations.migrate()

    store.add(Rule(id="w_local", tenant_id="local", symbol="BBCA",
                   metric="price_change_pct_1d", op=">", threshold=1.0,
                   channel="telegram:111"))
    store.add(Rule(id="w_friend", tenant_id="tg_42", symbol="BBRI",
                   metric="price_change_pct_1d", op=">", threshold=1.0,
                   channel="telegram:222"))


def test_interactive_listing_shows_only_the_callers_tenant(two_tenants,
                                                           monkeypatch):
    monkeypatch.setenv("FINANCE_TENANT", "local")
    assert [r.id for r in store.list_all()] == ["w_local"]
    monkeypatch.setenv("FINANCE_TENANT", "tg_42")
    assert [r.id for r in store.list_all()] == ["w_friend"]


def test_background_listing_crosses_tenants(two_tenants, monkeypatch):
    monkeypatch.setenv("FINANCE_TENANT", "local")
    assert {r.id for r in store.list_every_tenant()} == {"w_local", "w_friend"}


def test_cron_evaluation_fires_every_tenants_watches(two_tenants, monkeypatch):
    """The regression that motivated this: only 'local' would ever fire."""
    monkeypatch.setenv("FINANCE_TENANT", "local")
    monkeypatch.setattr(evaluator.metrics, "resolve",
                        _async_return(9999.0))
    sent: list[tuple[str, str | None]] = []

    async def fake_sender(text, chat_id=None):
        sent.append((text, chat_id))
        return True, None

    results = asyncio.run(evaluator.evaluate_once(sender=fake_sender))

    fired = {r["id"] for r in results if r["status"] == "fired"}
    assert fired == {"w_local", "w_friend"}
    # Each tenant's alert goes to its own channel, not a shared one.
    assert {chat for _, chat in sent} == {"111", "222"}


def _async_return(value):
    async def _fn(*a, **kw):
        return value
    return _fn
