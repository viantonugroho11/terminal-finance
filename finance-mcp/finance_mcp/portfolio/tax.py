"""Indonesian tax regime constants + helpers — ADR-0027.

All rates final (PPh final), applied at sell-side unless noted.
References: DGT PMK 34/2017 (IDX equity), PMK 68/2022 (crypto).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Regime:
    name: str
    equity_sell_pct: float       # PPh final on gross proceeds
    dividend_pct: float          # PPh final withheld
    crypto_buy_pct: float        # PPh 22 on gross buy
    crypto_sell_pct: float       # PPh 22 on gross sell
    crypto_vat_pct: float        # PPN on transaction


REGIMES: dict[str, Regime] = {
    "ID": Regime(
        name="ID",
        equity_sell_pct=0.001,   # 0.1%
        dividend_pct=0.10,
        crypto_buy_pct=0.0011,   # 0.11%
        crypto_sell_pct=0.0011,
        crypto_vat_pct=0.0011,   # PPN 0.11% each side
    ),
    "US": Regime(
        name="US",
        equity_sell_pct=0.0,     # capital gains reported separately
        dividend_pct=0.0,
        crypto_buy_pct=0.0,
        crypto_sell_pct=0.0,
        crypto_vat_pct=0.0,
    ),
}


def tax_on_sell(*, asset_class: str, gross_proceeds: float,
                regime: str = "ID") -> float:
    r = REGIMES.get(regime.upper()) or REGIMES["ID"]
    if asset_class.upper() == "CRYPTO":
        return gross_proceeds * (r.crypto_sell_pct + r.crypto_vat_pct)
    return gross_proceeds * r.equity_sell_pct


def tax_on_buy(*, asset_class: str, gross_cost: float,
               regime: str = "ID") -> float:
    r = REGIMES.get(regime.upper()) or REGIMES["ID"]
    if asset_class.upper() == "CRYPTO":
        return gross_cost * (r.crypto_buy_pct + r.crypto_vat_pct)
    return 0.0


def tax_on_dividend(*, gross_dividend: float, regime: str = "ID") -> float:
    r = REGIMES.get(regime.upper()) or REGIMES["ID"]
    return gross_dividend * r.dividend_pct
