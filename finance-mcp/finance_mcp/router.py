"""Capability + market router. See ADR-0012 and ADR-0021.

Picks a provider for a request based on:
  1. capability the caller wants
  2. market from SymbolResolver
  3. explicit per-(capability, market) preference (from
     config/finance.routing.yaml, or the built-in defaults below)
  4. tier priority (primary > aggregator > scraped > mock) as tie-breaker

Retries the declared fallback chain on retryable failures only.

Config file location precedence:
  1. FINANCE_ROUTING_CONFIG env
  2. /opt/data/config/finance.routing.yaml (container mount)
  3. <repo>/config/finance.routing.yaml
  4. built-in _DEFAULT_PREFERENCE below
"""
from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Any, Awaitable, Callable

from .errors import FinanceError, ErrorCode
from .resolver import MarketContext, resolve


log = logging.getLogger(__name__)


_TIER_RANK = {"primary": 0, "aggregator": 1, "scraped": 2, "mock": 3}

# Built-in default preference — used when no YAML config is found.
# Keep in lockstep with config/finance.routing.yaml so behaviour is
# identical whether or not the file is present.
_DEFAULT_PREFERENCE: dict[tuple[str, str], list[str]] = {
    # Indonesian equities.
    ("quote",             "IDX"): ["idx", "yahoo"],
    ("history",           "IDX"): ["idx", "yahoo"],
    ("company",           "IDX"): ["idx", "yahoo"],
    ("financials",        "IDX"): ["idx", "yahoo"],
    ("statements",        "IDX"): ["idx", "yahoo"],
    ("dividends",         "IDX"): ["idx"],
    ("corporate_actions", "IDX"): ["idx"],
    ("sector",            "IDX"): ["idx"],
    ("news",              "IDX"): ["yahoo"],

    # US / GLOBAL / CRYPTO — Yahoo owns all of these today.
    ("quote",             "US"):     ["yahoo"],
    ("history",           "US"):     ["yahoo"],
    ("company",           "US"):     ["yahoo"],
    ("financials",        "US"):     ["yahoo"],
    ("statements",        "US"):     ["yahoo"],
    ("news",              "US"):     ["yahoo"],

    ("quote",             "GLOBAL"): ["yahoo"],
    ("history",           "GLOBAL"): ["yahoo"],
    ("company",           "GLOBAL"): ["yahoo"],
    ("financials",        "GLOBAL"): ["yahoo"],
    ("statements",        "GLOBAL"): ["yahoo"],
    ("news",              "GLOBAL"): ["yahoo"],

    ("quote",             "CRYPTO"): ["yahoo"],
    ("history",           "CRYPTO"): ["yahoo"],
    ("news",              "CRYPTO"): ["yahoo"],

    # Untargeted (no symbol / market_overview / movers).
    ("market_overview",   "US"):     ["yahoo"],
    ("market_movers",     "US"):     ["yahoo"],

    # IDX-specific microstructure + market-wide.
    ("foreign_flow",         "IDX"):   ["idx"],
    ("search",               "IDX"):   ["idx"],
    ("broker_activity",      "IDX"):   ["idx"],
    ("order_book",           "IDX"):   ["idx"],
    ("ipo_calendar",         "IDX"):   ["idx"],
    ("trading_calendar",     "IDX"):   ["idx"],
    ("disclosures",          "IDX"):   ["idx"],
    ("board",                "IDX"):   ["idx"],
    ("shareholders",         "IDX"):   ["idx"],
    ("subsidiaries",         "IDX"):   ["idx"],
    ("idx_market_overview",  "IDX"):   ["idx"],
    ("idx_market_movers",    "IDX"):   ["idx"],

    # Macro — Indonesia. Bucket "MACRO" (no symbol).
    ("macro:bi_rate",      "MACRO"): ["bi"],
    ("macro:jisdor",       "MACRO"): ["bi"],
    ("macro:gdp",          "MACRO"): ["bps"],
    ("macro:cpi",          "MACRO"): ["bps"],
    ("macro:inflation",    "MACRO"): ["bps"],
    ("macro:unemployment", "MACRO"): ["bps"],
    ("macro:banking_spi",  "MACRO"): ["ojk"],
}


def _candidate_paths() -> list[Path]:
    out: list[Path] = []
    env = os.getenv("FINANCE_ROUTING_CONFIG", "").strip()
    if env:
        out.append(Path(env))
    out.append(Path("/opt/data/config/finance.routing.yaml"))
    # Repo-relative fallback (four levels up from this file).
    here = Path(__file__).resolve()
    out.append(here.parent.parent.parent.parent / "config" / "finance.routing.yaml")
    return out


def _load_preference() -> tuple[dict[tuple[str, str], list[str]], str | None]:
    """Return (preference-map, source-path). Falls back to defaults."""
    for p in _candidate_paths():
        try:
            if not p.exists():
                continue
            import yaml  # deferred so tests without pyyaml still import router
            payload = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception as e:
            log.warning("router: failed to load %s: %s — keeping defaults", p, e)
            return dict(_DEFAULT_PREFERENCE), None

        caps = (payload or {}).get("capabilities") or {}
        pref: dict[tuple[str, str], list[str]] = {}
        for cap_name, per_market in caps.items():
            if not isinstance(per_market, dict):
                continue
            for market, chain in per_market.items():
                if not isinstance(chain, list):
                    continue
                pref[(str(cap_name), str(market))] = [str(x) for x in chain]
        if pref:
            log.info("router: loaded %d preference entries from %s", len(pref), p)
            return pref, str(p)
    return dict(_DEFAULT_PREFERENCE), None


# Errors that stop the fallback chain (not transient).
_STOP_CODES = {
    ErrorCode.SYMBOL_NOT_FOUND,
    ErrorCode.INVALID_SYMBOL,
    ErrorCode.AUTHENTICATION_FAILED,
}


class Router:
    def __init__(self,
                 preference: dict[tuple[str, str], list[str]] | None = None,
                 config_source: str | None = None) -> None:
        self._providers: dict[str, Any] = {}
        if preference is None:
            preference, config_source = _load_preference()
        self._preference = preference
        self.config_source = config_source  # observable for diagnostics

    def register(self, provider: Any) -> None:
        if not getattr(provider, "name", None):
            raise ValueError("provider must have a .name")
        self._providers[provider.name] = provider

    def unregister(self, name: str) -> None:
        self._providers.pop(name, None)

    def providers(self) -> list[Any]:
        return list(self._providers.values())

    def preference(self) -> dict[tuple[str, str], list[str]]:
        return dict(self._preference)

    def validate(self) -> list[str]:
        """Return warnings: preference entries that reference no registered
        provider at all. Doesn't fail hard — an operator may deliberately
        toggle a provider off (FINANCE_IDX=off etc.)."""
        warnings: list[str] = []
        for (cap, mkt), chain in self._preference.items():
            missing = [n for n in chain if n not in self._providers]
            if missing == chain and chain:
                warnings.append(
                    f"routing[{cap!r}][{mkt!r}] references only unregistered "
                    f"providers {chain} — capability will be unroutable"
                )
        return warnings

    def chain(self, capability: str, market: str) -> list[Any]:
        """Ordered provider chain for (capability, market). Pure."""
        # 1) Explicit preference table wins.
        pref = self._preference.get((capability, market), [])
        ordered: list[Any] = []
        seen: set[str] = set()
        for name in pref:
            p = self._providers.get(name)
            if p is None:
                continue
            if capability in getattr(p, "capabilities", set()) \
               and market in getattr(p, "markets", set()):
                ordered.append(p); seen.add(p.name)

        # 2) Fill with any other providers that declare (capability, market),
        #    tier-sorted, so a newly-registered provider still gets a shot.
        remaining = [
            p for p in self._providers.values()
            if p.name not in seen
            and capability in getattr(p, "capabilities", set())
            and market in getattr(p, "markets", set())
        ]
        remaining.sort(key=lambda p: _TIER_RANK.get(getattr(p, "tier", "scraped"), 99))
        return ordered + remaining

    async def call(
        self,
        capability: str,
        *,
        symbol: str | None = None,
        market: str | None = None,
        fetch: Callable[[Any], Awaitable[Any]],
    ) -> tuple[Any, Any, MarketContext | None]:
        """Return (value, chosen_provider, market_context).

        `fetch(provider)` is the per-provider adapter call. Router owns
        chain selection + fallback; caller owns cache and provenance
        wrapping (which needs `chosen_provider` and `market_context`).
        """
        ctx: MarketContext | None = None
        if symbol is not None:
            ctx = resolve(symbol)
            mkt = market or ctx.market
        elif market is not None:
            mkt = market
        else:
            mkt = "US"  # default bucket for symbol-less calls

        chain = self.chain(capability, mkt)
        if not chain:
            raise FinanceError(
                ErrorCode.DATA_UNAVAILABLE,
                f"No provider satisfies capability={capability} market={mkt}",
                provider="router", symbol=symbol,
            )

        last: FinanceError | None = None
        for provider in chain:
            try:
                value = await fetch(provider)
                return value, provider, ctx
            except FinanceError as e:
                last = e
                if e.code in _STOP_CODES:
                    raise
                log.warning("router: %s failed capability=%s market=%s: %s",
                            provider.name, capability, mkt, e)
                continue

        assert last is not None
        raise last
