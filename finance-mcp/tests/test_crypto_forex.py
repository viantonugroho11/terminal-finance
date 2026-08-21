"""ADR-0031 — CryptoProvider, CoinglassProvider, JISDOR, forward CIP."""
from __future__ import annotations

import asyncio

import pytest
from finance_mcp.calc import fx_forward_via_cip
from finance_mcp.providers.coinglass import CoinglassProvider
from finance_mcp.providers.crypto import CryptoProvider

# ── crypto OHLCV parse (Binance shape) ─────────────────────────────────

_BINANCE_KLINES = [
    # [openTime, open, high, low, close, volume, closeTime, ...]
    [1_700_000_000_000, "37000.00", "37500.00", "36800.00",
     "37400.00", "12.5", 1_700_003_599_999, "0", 0, "0", "0", "0"],
    [1_700_003_600_000, "37400.00", "37800.00", "37200.00",
     "37700.00", "10.0", 1_700_007_199_999, "0", 0, "0", "0", "0"],
]


def test_ohlcv_binance_parses_candles() -> None:
    async def fake(url: str, params: dict):
        assert "klines" in url
        assert params.get("symbol") == "BTCUSDT"
        return _BINANCE_KLINES

    prov = CryptoProvider(fetcher=fake)
    out = asyncio.run(prov.ohlcv("BTCUSDT", exchange="binance",
                                 timeframe="1h", limit=100))
    assert out.symbol == "BTCUSDT"
    assert out.exchange == "binance"
    assert len(out.candles) == 2
    assert out.candles[0].close == 37400.0
    assert out.candles[1].volume == 10.0


def test_ohlcv_unknown_exchange_raises() -> None:
    from finance_mcp.errors import ErrorCode, FinanceError
    prov = CryptoProvider(fetcher=lambda *a, **k: None)
    with pytest.raises(FinanceError) as exc:
        asyncio.run(prov.ohlcv("BTCUSDT", exchange="mexc"))
    assert exc.value.code == ErrorCode.PROVIDER_UNAVAILABLE


# ── crypto order book ──────────────────────────────────────────────────

def test_orderbook_binance_parses() -> None:
    async def fake(url: str, params: dict):
        return {"bids": [["37000", "1.5"], ["36999", "0.5"]],
                "asks": [["37010", "2.0"], ["37020", "1.0"]]}

    prov = CryptoProvider(fetcher=fake)
    ob = asyncio.run(prov.orderbook("BTCUSDT", exchange="binance", depth=2))
    assert len(ob.bids) == 2 and len(ob.asks) == 2
    assert ob.bids[0].price == 37000.0
    assert ob.bids[0].quantity == 1.5


def test_orderbook_indodax_maps_buy_sell() -> None:
    async def fake(url: str, params: dict):
        assert "depth" in url
        return {"buy": [["550000000", "0.1"]],
                "sell": [["551000000", "0.2"]]}

    prov = CryptoProvider(fetcher=fake)
    ob = asyncio.run(prov.orderbook("BTCIDR", exchange="indodax"))
    assert ob.bids[0].price == 550_000_000
    assert ob.asks[0].quantity == 0.2


# ── stablecoin peg ─────────────────────────────────────────────────────

def test_peg_positive_when_above_one() -> None:
    async def fake(url: str, params: dict):
        return {"price": "1.0005"}

    prov = CryptoProvider(fetcher=fake)
    peg = asyncio.run(prov.stablecoin_peg("USDC"))
    assert peg.symbol == "USDC"
    assert peg.price == pytest.approx(1.0005)
    assert peg.deviation_bps == pytest.approx(5.0)


def test_peg_rejects_non_stablecoin() -> None:
    from finance_mcp.errors import ErrorCode, FinanceError
    prov = CryptoProvider(fetcher=lambda *a, **k: None)
    with pytest.raises(FinanceError) as exc:
        asyncio.run(prov.stablecoin_peg("BTC"))
    assert exc.value.code == ErrorCode.INVALID_SYMBOL


# ── coinglass ──────────────────────────────────────────────────────────

def test_perp_funding_parses() -> None:
    async def fake(path: str, params: dict):
        assert path.endswith("funding-rate/history")
        return {"data": [{"fundingRate": "0.0001",
                          "nextFundingTime": "2026-08-14T00:00:00Z"}]}

    prov = CoinglassProvider(fetcher=fake)
    f = asyncio.run(prov.perp_funding("BTC"))
    assert f.rate == pytest.approx(0.0001)
    assert f.exchange == "binance"


def test_perp_funding_empty_raises() -> None:
    from finance_mcp.errors import ErrorCode, FinanceError

    async def fake(path: str, params: dict):
        return {"data": []}

    prov = CoinglassProvider(fetcher=fake)
    with pytest.raises(FinanceError) as exc:
        asyncio.run(prov.perp_funding("BTC"))
    assert exc.value.code == ErrorCode.DATA_UNAVAILABLE


def test_perp_oi_parses() -> None:
    async def fake(path: str, params: dict):
        return {"data": {"oiBase": "50000.5", "oiUsd": "1850000000",
                         "h24Change": "3.2"}}

    prov = CoinglassProvider(fetcher=fake)
    oi = asyncio.run(prov.perp_open_interest("BTC"))
    assert oi.oi_base == pytest.approx(50_000.5)
    assert oi.oi_usd == pytest.approx(1_850_000_000)
    assert oi.change_24h_pct == pytest.approx(3.2)


# ── CIP forward ────────────────────────────────────────────────────────

def test_cip_forward_dom_higher_gives_premium() -> None:
    # USDIDR spot 16000, dom (IDR) 6.25%, for (USD) 5.25%, 90d/360
    fwd, points = fx_forward_via_cip(
        spot=16_000.0, rate_dom_annual=0.0625,
        rate_for_annual=0.0525, tenor_days=90,
    )
    assert fwd > 16_000.0
    assert points == pytest.approx(fwd - 16_000.0)


def test_cip_forward_zero_tenor_equals_spot() -> None:
    fwd, points = fx_forward_via_cip(
        spot=16_000.0, rate_dom_annual=0.06,
        rate_for_annual=0.05, tenor_days=0,
    )
    assert fwd == pytest.approx(16_000.0)
    assert points == pytest.approx(0.0)


def test_cip_forward_negative_tenor_raises() -> None:
    with pytest.raises(ValueError):
        fx_forward_via_cip(spot=1, rate_dom_annual=0, rate_for_annual=0,
                           tenor_days=-1)
