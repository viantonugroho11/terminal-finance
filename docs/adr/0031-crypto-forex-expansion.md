# ADR-0031: Crypto + forex expansion — deep coverage beyond spot quote

- Status: Proposed
- Date: 2026-08-14
- Deciders: Finance Terminal team

## Context

Today crypto = single provider spot quote (`get_quote BTC`). Forex = Yahoo pair quote (`USDIDR=X`). Real user questions go further:

**Crypto:**
- Historical OHLCV across venues (Binance, Coinbase, Kraken, Indodax for IDR pairs).
- On-chain metrics (active addresses, exchange netflow, funding rate) — signal alpha.
- Stablecoin flow (USDT/USDC market cap, peg deviation).
- Derivatives (perp funding, open interest, basis) — regime signal.
- Fiat-onramp specific: IDR pairs on Indodax + Tokocrypto, spread + volume.

**Forex:**
- Cross rates across majors + IDR crosses.
- Historical fixings (BI JISDOR daily reference rate for IDR — regulatory reference).
- Forward points (implied by rate differential).
- Central-bank calendar (Fed, ECB, BoJ, BI) already partly covered via `get_bi_rate`; extend to global.

Underserved: Indonesian users care about BTC/IDR spread, USDT/IDR peg, IDR JISDOR — no single tool answers.

## Decision

Extend provider set and capabilities. Two new providers, one extension.

**New providers:**

1. **`CcxtProvider`** — wraps `ccxt` library for multi-venue crypto OHLCV + orderbook. Exchanges v1: Binance, Coinbase, Kraken, Indodax. Rate-limit-aware; public endpoints only (no keys).
2. **`CoinglassProvider`** — derivatives + on-chain aggregates (funding, OI, netflow). Public tier; API key optional for higher limits.

**Extension:**

3. **`BiProvider.jisdor_rate(date?)`** — daily IDR reference rate scraper.
4. **`YahooProvider`** already covers G10 FX historical; keep as fallback.

**New capabilities:**

| Capability             | Tool                        | Provider    | TTL   |
|------------------------|-----------------------------|-------------|-------|
| `crypto_ohlcv_venue`   | `get_crypto_ohlcv(sym,ex)`  | ccxt        | 1min  |
| `crypto_orderbook`     | `get_crypto_orderbook`      | ccxt        | 10s   |
| `crypto_funding`       | `get_perp_funding`          | coinglass   | 5min  |
| `crypto_open_interest` | `get_perp_oi`               | coinglass   | 5min  |
| `stablecoin_peg`       | `get_stablecoin_peg`        | ccxt        | 1min  |
| `fx_cross`             | `get_fx_cross(base,quote)`  | yahoo       | 1min  |
| `fx_jisdor`            | `get_jisdor_rate(date?)`    | bi          | 1d    |
| `fx_forward_points`    | `get_fx_forward(pair,tenor)`| yahoo+calc  | 5min  |

**New skills:**

- `crypto-deep` extends existing `crypto-analysis` with derivatives + on-chain.
- `fx-analysis` new: spot + forward + JISDOR + central-bank stance.

## Consequences

- Positive: differentiates from generic crypto trackers — Indonesian IDR-pair depth + JISDOR is unique.
- Positive: on-chain + derivatives cover the "regime" signal that spot alone misses.
- Positive: ccxt gives multi-venue arbitrage/spread visibility for free.
- Negative: coinglass free tier limited — add API key config, degrade gracefully.
- Negative: ccxt is a heavy dep; contain to its own module, lazy-import in provider.
- Negative: derivatives data has legal/regulatory sensitivity in Indonesia (Bappebti scope). No trading tools; read-only analysis only, disclaimer in skill output.
- Negative: forex forwards from rate differential are approximations, not tradable quotes. Provenance must say so.
- Follow-ups: refresh `symbol_resolver.py` for crypto venue prefix (`BINANCE:BTCUSDT`), integration test per exchange, cost cap for coinglass calls, JISDOR historical backfill.

## Alternatives considered

- **CoinGecko / CoinMarketCap only.** Rejected: aggregated, misses per-venue spread + IDR pairs; no derivatives.
- **Direct exchange REST per provider.** Rejected: ccxt already normalizes; DIY is duplicated effort for marginal gain.
- **Paid data (Kaiko, Amberdata).** Rejected v1: cost + closed data.
- **Skip derivatives, spot only.** Rejected: funding + OI are the highest-signal crypto metrics; skipping them keeps terminal a beginner tool.

## References

- ADR-0008 (multi-provider).
- ADR-0020 (Indonesian providers) — BI extension pattern.
- ADR-0027 (portfolio + tax) — depends on FX at trade time.
