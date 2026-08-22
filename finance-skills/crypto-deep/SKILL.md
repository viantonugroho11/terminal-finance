---
name: crypto-deep
description: Deep crypto analysis — multi-venue OHLCV, order book, funding rate, open interest, stablecoin peg, IDR pairs on Indodax. Use when user says "BTC funding", "OI", "spread IDR", "peg USDT".
version: 0.1.0
author: Finance Hermes
license: AGPL-3.0-only
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, Crypto, Derivatives, Indonesia]
    related_skills: [crypto-analysis, watch, market-overview]
    requires_tools:
      - finance.get_crypto_ohlcv
      - finance.get_crypto_orderbook
      - finance.get_perp_funding
      - finance.get_perp_oi
      - finance.get_stablecoin_peg
---

# Crypto Deep

Composed answer for a crypto symbol: spot (via existing get_quote),
Binance vs Indodax IDR spread, perp funding + open interest, and
stablecoin peg if the symbol is a stablecoin.

## When to Use

- "BTC funding + OI Binance"
- "spread BTCIDR Indodax vs Binance"
- "USDT peg sekarang"
- "ETH open interest 24 jam"

## Flow

1. Normalize symbol (BTC → BTCUSDT for Binance perps, BTCIDR for
   Indodax).
2. Parallel:
   - `finance.get_crypto_ohlcv(symbol, exchange, timeframe='1h', limit=24)`
     per venue user cares about.
   - `finance.get_perp_funding(symbol)` + `finance.get_perp_oi(symbol)`
     if user asks derivatives.
   - `finance.get_stablecoin_peg(symbol)` if `symbol in {USDT,USDC,...}`.
3. Compose narrative: last close per venue, cross-venue spread bps,
   funding sign + magnitude, OI 24h change, peg deviation bps.

## Rules

- Do NOT solicit or accept exchange API keys. Public endpoints only.
- Bappebti-regulated disclaimer required: prepend
  "Bukan saran investasi. Derivatif crypto tunduk pengawasan Bappebti."
- Funding is 8-hour rate; annualize as `rate * 3 * 365` and label as
  "annualized approximation" — never as tradable rate.
- Stablecoin peg deviation reported in bps; do NOT round to zero when
  |dev| < 10bps — precision matters near the peg.
