"""SymbolResolver — ADR-0021."""
from finance_mcp.resolver import MarketContext, resolve


def test_us_default():
    r = resolve("AAPL")
    assert r.market == "US" and r.currency == "USD"
    assert r.canonical_symbol == "AAPL"
    assert r.source == "default"


def test_idx_via_allowlist():
    r = resolve("BBCA")
    assert r.market == "IDX" and r.country == "ID" and r.currency == "IDR"
    assert r.canonical_symbol == "BBCA.JK"
    assert r.source == "allowlist"


def test_idx_via_suffix_wins_over_allowlist():
    r = resolve("BBCA.JK")
    assert r.market == "IDX" and r.canonical_symbol == "BBCA.JK"
    assert r.source == "suffix"


def test_idx_lowercase_and_whitespace():
    r = resolve("  bbri  ")
    assert r.market == "IDX" and r.canonical_symbol == "BBRI.JK"


def test_unknown_4_letter_falls_through_to_us():
    r = resolve("ZZZZ")
    assert r.market == "US"


def test_crypto_pattern():
    r = resolve("BTC-USD")
    assert r.market == "CRYPTO" and r.source == "crypto"


def test_empty_symbol_safe():
    r = resolve("")
    assert r.market == "US" and r.canonical_symbol == ""


def test_multiple_idx_tickers_hit_allowlist():
    for t in ("BBRI", "BMRI", "TLKM", "ASII", "ANTM", "GOTO", "UNVR", "ICBP"):
        r = resolve(t)
        assert r.market == "IDX", f"{t} should resolve to IDX"
        assert r.canonical_symbol == f"{t}.JK"


def test_context_to_dict_shape():
    d = resolve("BBCA").to_dict()
    assert set(d) == {"market", "country", "currency", "canonical_symbol", "source"}


def test_hk_suffix_routes_global_not_idx():
    r = resolve("0700.HK")
    assert r.market == "GLOBAL" and r.currency == "HKD"


def test_frozen_dataclass():
    r = resolve("AAPL")
    try:
        r.market = "IDX"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("MarketContext should be frozen")


def test_marketcontext_direct_instantiation():
    m = MarketContext("IDX", "ID", "IDR", "BBCA.JK", "allowlist")
    assert m.to_dict()["market"] == "IDX"
