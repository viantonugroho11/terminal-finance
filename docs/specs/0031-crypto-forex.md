# Spec: Crypto + forex expansion

Ref: ADR-0031.

## Goal

Deep crypto (multi-venue OHLCV, derivatives, on-chain, IDR pairs) + deep forex (crosses, JISDOR, forward points).

## Success conditions

- `pytest finance-mcp/tests/test_ccxt_provider.py`, `test_coinglass_provider.py`, `test_jisdor.py` green.
- New tools return provenance with exchange + venue tag.
- `crypto-deep` skill answers "BTC funding + OI + IDR spread" in one call.
- `fx-analysis` skill answers "USDIDR spot + JISDOR today + forward 1M" in one call.

## Deliverables

### 1. Provider `CcxtProvider`

Path: `finance-mcp/finance_mcp/providers/ccxt_provider.py`.

Wraps `ccxt` library. Exchanges v1: `binance`, `coinbase`, `kraken`, `indodax`.

Methods:
- `ohlcv(symbol, exchange, timeframe, since, limit)`
- `orderbook(symbol, exchange, depth=20)`
- `stablecoin_peg(symbol) -> {price, deviation_bps}`

Rate limit via ccxt built-in. Public endpoints only (no keys).

### 2. Provider `CoinglassProvider`

Path: `finance-mcp/finance_mcp/providers/coinglass.py`.

Methods:
- `perp_funding(symbol) -> {exchange, rate, next_at}`
- `perp_open_interest(symbol) -> {exchange, oi_usd, change_24h_pct}`
- `exchange_netflow(symbol, window) -> {inflow, outflow, net}`

API key optional: env `COINGLASS_API_KEY`; degrades to free tier limits when absent.

### 3. `BiProvider` extension

Add `jisdor_rate(date=None)`. Source: BI website daily JISDOR CSV. Cache 1d.

### 4. Forward points calc

Path: `finance-mcp/finance_mcp/calc.py` — `fx_forward_points(pair, tenor_days, spot, rate_dom, rate_for)` using covered interest parity. Marked as `derived` in provenance.

### 5. MCP tools

Per ADR-0031 table:
- `get_crypto_ohlcv(symbol, exchange, timeframe, ...)`
- `get_crypto_orderbook(symbol, exchange)`
- `get_perp_funding(symbol)`
- `get_perp_oi(symbol)`
- `get_stablecoin_peg(symbol)`
- `get_fx_cross(base, quote)`
- `get_jisdor_rate(date=None)`
- `get_fx_forward(pair, tenor)`

### 6. Router additions

Path: `finance-mcp/finance_mcp/router.py`.

- `(crypto_ohlcv_venue, CRYPTO) -> ccxt`
- `(crypto_funding, CRYPTO) -> coinglass`
- `(fx_jisdor, GLOBAL) -> bi`
- Others per table.

### 7. Symbol resolver

Extend `symbol_resolver.py`:
- Crypto venue prefix: `BINANCE:BTCUSDT`, `INDODAX:BTCIDR`.
- Fallback: bare `BTC` → default exchange from `CRYPTO_DEFAULT_EXCHANGE` env.

### 8. Skills

- `crypto-deep` (`finance-skills/crypto-deep/SKILL.md`) — composes spot + venue-spread + funding + OI + netflow + peg (if stablecoin).
- `fx-analysis` (`finance-skills/fx-analysis/SKILL.md`) — spot + JISDOR + forward + central-bank stance + BI Rate context.

### 9. Legal disclaimers

Skills output prepends: "Bukan saran investasi. Data derivatif crypto tunduk pengawasan Bappebti." Configurable per locale.

## Out of scope v1

- Trading tools (read-only).
- Options chain.
- DeFi TVL / DEX data.

## Milestones

1. ccxt provider + 4 exchanges + tests (1.5d).
2. Coinglass provider + rate limit + tests (1d).
3. JISDOR scraper + BiProvider extension (0.5d).
4. Forward calc + provenance (0.5d).
5. Router + resolver updates + tests (0.5d).
6. Tools registered + integration tests (1d).
7. `crypto-deep` + `fx-analysis` skills + templates (1d).

Total: ~6d.
