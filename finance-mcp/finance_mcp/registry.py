"""Process-wide Router singleton and provider facade.

Split out from server.py so both server-side MCP tools and internal
services (portfolio, subagent-shim, etc.) share the same router without
a circular import.
"""
from __future__ import annotations
import os
from typing import Any

from .providers.mock import MockProvider
from .providers.yahoo import YahooProvider
from .providers.idx import IdxProvider
from .providers.bi import BiProvider
from .providers.bps import BpsProvider
from .providers.ojk import OjkProvider
from .providers.sec import SecProvider
from .providers.ksei import KseiProvider
from .retry import with_retry
from .router import Router


def build_router() -> Router:
    """Register providers. Overridable via FINANCE_PROVIDER=mock for tests."""
    r = Router()
    mode = os.getenv("FINANCE_PROVIDER", "auto").lower()
    if mode == "mock":
        r.register(MockProvider())
        return r
    r.register(YahooProvider())
    if os.getenv("FINANCE_IDX", "on").lower() != "off":
        r.register(IdxProvider())
    if os.getenv("FINANCE_BI", "on").lower() != "off":
        r.register(BiProvider())
    if os.getenv("FINANCE_BPS", "on").lower() != "off":
        r.register(BpsProvider())
    if os.getenv("FINANCE_OJK", "on").lower() != "off":
        r.register(OjkProvider())
    if os.getenv("FINANCE_SEC", "on").lower() != "off":
        r.register(SecProvider())
    if os.getenv("FINANCE_KSEI", "on").lower() != "off":
        r.register(KseiProvider())
    return r


router: Router = build_router()


async def routed_quote(symbol: str):
    """Router-driven quote — respects market resolver + fallback chain."""
    async def _fetch(p):
        return await with_retry(lambda: p.quote(symbol),
                                provider=p.name, symbol=symbol)
    value, _, _ = await router.call("quote", symbol=symbol, fetch=_fetch)
    return value


async def routed_history(symbol: str, period: str = "6mo",
                         interval: str = "1d"):
    async def _fetch(p):
        return await with_retry(lambda: p.history(symbol, period, interval),
                                provider=p.name, symbol=symbol)
    value, _, _ = await router.call("history", symbol=symbol, fetch=_fetch)
    return value


async def routed_company(symbol: str):
    async def _fetch(p):
        return await with_retry(lambda: p.company(symbol),
                                provider=p.name, symbol=symbol)
    value, _, _ = await router.call("company", symbol=symbol, fetch=_fetch)
    return value
