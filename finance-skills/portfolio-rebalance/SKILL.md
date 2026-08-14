---
name: portfolio-rebalance
description: Lot-level portfolio with FIFO/HIFO cost basis, Indonesian tax awareness, and rebalance plans. Use when user says "rebalance", "porto", "posisi", "cost basis", "realized PnL".
version: 0.1.0
author: Finance Hermes
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, Portfolio, Tax, Rebalance]
    related_skills: [portfolio-analysis, risk-analysis, market-overview]
    requires_tools:
      - finance.record_trade
      - finance.list_lots
      - finance.get_unrealized_pnl
      - finance.get_realized_pnl
      - finance.rebalance_plan
---

# Portfolio Rebalance (lot-level)

Lot-tracked portfolio: every buy is a lot; every sell matches lots via
FIFO / LIFO / HIFO. Realized PnL is after-tax under configurable
regime (default ID). Rebalance plan proposes trades to reach target
weights within tolerance.

## When to Use

- "record buy BBCA 100 @ 9500"
- "rebalance porto target 40% equity 30% bond 20% cash 10% crypto"
- "unrealized PnL"
- "realized PnL YTD after tax"
- "cost basis BBCA"

## Flow

- **Record trade:** `finance.record_trade(kind='BUY'|'SELL', symbol, qty, price, ...)`.
  For sells, method defaults to FIFO; user may specify HIFO for lowest
  tax realization.
- **Unrealized:** `finance.get_unrealized_pnl()` — pulls live quotes for
  held symbols; omits price if unavailable rather than guessing.
- **Realized:** `finance.get_realized_pnl(regime='ID')` — per-symbol
  breakdown + after-tax total.
- **Rebalance:** `finance.rebalance_plan(targets={'BBCA':0.4,'BTC':0.1,...}, cash=...)`.
  Weights must sum to 1.0. Tool returns list of BUY/SELL trades with
  drift %, notional, and tax cost estimate per trade.

## Rules

- NEVER call `record_trade` without user confirmation (state ticker,
  qty, price back).
- ALWAYS show tax cost when suggesting a sell.
- Tax figures are deterministic estimates from the calc module — do not
  round differently or paraphrase the regime rates.
- If `total_market_value` is missing (all quotes failed), refuse to
  present a rebalance plan; ask user for manual price input.
- Indonesian regime: 0.1% PPh final on equity sell proceeds, 10%
  dividend, 0.11% PPh 22 + 0.11% PPN on crypto both sides. Do not
  invent additional taxes.
