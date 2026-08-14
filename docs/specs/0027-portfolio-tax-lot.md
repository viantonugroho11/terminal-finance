# Spec: Portfolio lot-tracking + Indonesian tax + rebalance

Ref: ADR-0027.

## Goal

Log trades per lot, compute realized/unrealized PnL under Indonesian tax regime, suggest rebalance trades that respect tax drag.

## Success conditions

- `pytest finance-mcp/tests/test_portfolio.py` green: FIFO/HIFO, PnL, PPh calc, rebalance optimality.
- Migration script converts existing flat holdings to lots without data loss.
- Rebalance plan is deterministic (same input → same output).

## Deliverables

### 1. Store

Path: `~/.hermes/finance/portfolio/lots.jsonl` (append-only).

Buy line:
```json
{"kind":"buy","lot_id":"l_01H...","symbol":"BBCA","qty":100,"price":9500,"currency":"IDR","fee":1000,"tax":0,"acquired_at":"2026-08-14T02:00:00Z","account":"main"}
```

Sell line:
```json
{"kind":"sell","lot_id":"l_01H...","close_lot_id":"l_01H...prev","qty":100,"price":9800,"currency":"IDR","fee":1000,"tax":980,"closed_at":"2026-08-14T04:00:00Z"}
```

### 2. Calc module

Path: `finance-mcp/finance_mcp/portfolio.py`.

Functions (pure):
- `cost_basis(lots, method="FIFO"|"HIFO")`
- `unrealized_pnl(lots, quotes, base_ccy)`
- `realized_pnl(lots, method, base_ccy)`
- `after_tax_return(lots, regime="ID"|"US", base_ccy)`
- `rebalance_plan(lots, quotes, targets: dict[str,float], tolerance=0.02) -> list[Trade]`

Rebalance: minimize `sum(trade_notional) + tax_cost` s.t. `|w_i - target_i| <= tolerance`. Solver: `scipy.optimize.linprog` (LP formulation) — deterministic.

### 3. Indonesian tax rules

Constants in `portfolio_tax.py`:
- IDX sell: 0.1% final on gross proceeds.
- Dividend IDX: 10% final withheld.
- Crypto (Bappebti): 0.11% PPh 22 + 0.11% PPN on gross buy+sell.

### 4. MCP tools

- `record_trade(kind, symbol, qty, price, currency, ...)`
- `list_lots(symbol?, open_only=True)`
- `get_unrealized_pnl(base_ccy="IDR")`
- `get_realized_pnl(base_ccy="IDR", period="ytd")`
- `rebalance_plan(targets: dict, method="FIFO")`

### 5. Skill `portfolio-rebalance`

Composes: list lots + quotes + FX + plan + explain tax cost per proposed sell. Warns "sell BBCA lot X → PPh 0.1% ≈ Rp X".

### 6. Migration

Script: `scripts/migrate_portfolio_v1_to_v2.py` — reads existing holdings JSON, creates one synthetic buy lot per position with `acquired_at="unknown"` flag.

## Out of scope

- Full MPT / Black-Litterman.
- Broker API integration (manual trade entry only).

## Milestones

1. Lot schema + JSONL read/write + migration (1d).
2. Cost-basis + PnL + tax calc + tests (1.5d).
3. FX-at-trade wiring (depends on ADR-0031) (0.5d).
4. Rebalance LP + determinism test (1d).
5. Tools + skill + tests (1d).

Total: ~5d.
