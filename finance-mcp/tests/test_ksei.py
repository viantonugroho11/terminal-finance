"""KseiProvider — ADR-0026. Uses injected fetcher (no network)."""
from __future__ import annotations

import asyncio

import pytest
from finance_mcp.providers.ksei import KseiProvider, parse_csv

_CSV = (
    "Code,AsOf,ForeignPct,DomesticPct,LocalInstitutionalPct,RetailPct,TotalShares\n"
    "BBCA,2026-07-31,42.15,57.85,38.20,19.65,246000000000\n"
    "TLKM,2026-07-31,30.10,69.90,50.00,19.90,99000000000\n"
)


def test_parse_csv_finds_symbol() -> None:
    o = parse_csv(_CSV, "BBCA")
    assert o is not None
    assert o.symbol == "BBCA.JK"
    assert o.foreign_pct == pytest.approx(42.15)
    assert o.retail_pct == pytest.approx(19.65)
    assert o.total_shares == 246_000_000_000


def test_parse_csv_missing_returns_none() -> None:
    assert parse_csv(_CSV, "ASII") is None


def test_provider_uses_injected_fetcher() -> None:
    async def fake_fetch(sym: str) -> str:
        return _CSV

    prov = KseiProvider(fetcher=fake_fetch)
    result = asyncio.run(prov.ownership_breakdown("BBCA"))
    assert result.foreign_pct == pytest.approx(42.15)


def test_provider_raises_on_unknown_symbol() -> None:
    from finance_mcp.errors import ErrorCode, FinanceError

    async def fake_fetch(sym: str) -> str:
        return _CSV

    prov = KseiProvider(fetcher=fake_fetch)
    with pytest.raises(FinanceError) as exc:
        asyncio.run(prov.ownership_breakdown("ZZZZ"))
    assert exc.value.code == ErrorCode.DATA_UNAVAILABLE
