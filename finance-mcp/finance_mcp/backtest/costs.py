"""Transaction cost + slippage model per market — ADR-0029."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    market: str
    commission_pct: float
    commission_flat_per_share: float
    slippage_bps: float          # applied to fill price
    sell_tax_pct: float          # PPh final on gross proceeds (ID equity)


COST_MODELS: dict[str, CostModel] = {
    "ID": CostModel(
        market="ID",
        commission_pct=0.0015,               # 0.15% broker commission
        commission_flat_per_share=0.0,
        slippage_bps=5.0,
        sell_tax_pct=0.001,                  # 0.1% PPh final
    ),
    "US": CostModel(
        market="US",
        commission_pct=0.0,
        commission_flat_per_share=0.005,
        slippage_bps=2.0,
        sell_tax_pct=0.0,
    ),
    "CRYPTO": CostModel(
        market="CRYPTO",
        commission_pct=0.001,
        commission_flat_per_share=0.0,
        slippage_bps=3.0,
        sell_tax_pct=0.0022,                 # 0.11% + 0.11% VAT
    ),
}


def fill_price(*, base_price: float, side: str, market: str) -> float:
    """Apply slippage to the mid: buys pay above, sells receive below."""
    m = COST_MODELS.get(market.upper()) or COST_MODELS["ID"]
    slip = base_price * m.slippage_bps / 10_000.0
    return base_price + slip if side.upper() == "BUY" else base_price - slip


def transaction_cost(*, notional: float, qty: float, side: str,
                     market: str) -> float:
    """Commission + per-share + sell-tax if applicable."""
    m = COST_MODELS.get(market.upper()) or COST_MODELS["ID"]
    fee = notional * m.commission_pct + qty * m.commission_flat_per_share
    if side.upper() == "SELL":
        fee += notional * m.sell_tax_pct
    return fee
