"""Symbol resolver — maps a raw ticker to a MarketContext.

Deterministic, dependency-free. See ADR-0021.

Order of precedence:
  1. Explicit market suffix (.JK, -USD, ...).
  2. IDX 4-letter ticker allowlist (data/idx_tickers.txt).
  3. Crypto pattern (SYM-USD, SYM-USDT).
  4. Default → US equity.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


Market = Literal["US", "IDX", "GLOBAL", "CRYPTO"]


@dataclass(frozen=True)
class MarketContext:
    market: Market
    country: str          # ISO 3166-1 alpha-2
    currency: str         # ISO 4217
    canonical_symbol: str
    source: Literal["suffix", "allowlist", "crypto", "default"]

    def to_dict(self) -> dict:
        return {
            "market": self.market,
            "country": self.country,
            "currency": self.currency,
            "canonical_symbol": self.canonical_symbol,
            "source": self.source,
        }


_ALLOWLIST_PATH = Path(__file__).parent / "data" / "idx_tickers.txt"


def _load_allowlist(path: Path = _ALLOWLIST_PATH) -> frozenset[str]:
    if not path.exists():
        return frozenset()
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.split("#", 1)[0].strip().upper()
        if s and s.isalpha() and len(s) == 4:
            out.add(s)
    return frozenset(out)


_IDX_ALLOWLIST: frozenset[str] = _load_allowlist()

# Suffixes we recognize explicitly. Only .JK routed to IDX for now.
_SUFFIX_MAP: dict[str, tuple[Market, str, str]] = {
    ".JK": ("IDX", "ID", "IDR"),
    ".HK": ("GLOBAL", "HK", "HKD"),
    ".L":  ("GLOBAL", "GB", "GBP"),
    ".T":  ("GLOBAL", "JP", "JPY"),
    ".SS": ("GLOBAL", "CN", "CNY"),
    ".SZ": ("GLOBAL", "CN", "CNY"),
}


def _is_crypto(sym: str) -> bool:
    u = sym.upper()
    return u.endswith("-USD") or u.endswith("-USDT") or u.endswith("-USDC")


def reload_allowlist(path: Path | None = None) -> frozenset[str]:
    """Test helper — force reload with a different path or after edit."""
    global _IDX_ALLOWLIST
    _IDX_ALLOWLIST = _load_allowlist(path or _ALLOWLIST_PATH)
    return _IDX_ALLOWLIST


def resolve(symbol: str, *, allowlist: frozenset[str] | None = None) -> MarketContext:
    """Classify a symbol. Pure. See module docstring for order."""
    raw = (symbol or "").strip()
    if not raw:
        # Empty falls through to default so caller error paths stay predictable.
        return MarketContext("US", "US", "USD", "", "default")

    s = raw.upper()

    # 1) Explicit suffix.
    for suf, (mkt, ctry, cur) in _SUFFIX_MAP.items():
        if s.endswith(suf):
            return MarketContext(mkt, ctry, cur, s, "suffix")

    # 2) Crypto pattern.
    if _is_crypto(s):
        return MarketContext("CRYPTO", "XX", "USD", s, "crypto")

    # 3) IDX allowlist (unsuffixed 4-letter uppercase).
    src = allowlist if allowlist is not None else _IDX_ALLOWLIST
    if len(s) == 4 and s.isalpha() and s in src:
        return MarketContext("IDX", "ID", "IDR", f"{s}.JK", "allowlist")

    # 4) Default = US equity.
    return MarketContext("US", "US", "USD", s, "default")
