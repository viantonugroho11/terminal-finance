---
name: flow-analysis
description: IDX smart-money view — foreign flow + broker aggregate + insider trades + ownership breakdown. Use when user asks "aliran dana", "smart money", "asing", "insider", "kepemilikan".
version: 0.1.0
author: Finance Hermes
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, IDX, Flow, Institutional]
    related_skills: [stock-analysis, market-overview, watch]
    requires_tools:
      - finance.get_foreign_flow
      - finance.get_broker_flow_aggregate
      - finance.get_insider_trades
      - finance.get_major_holder_changes
      - finance.get_ownership_breakdown
---

# Flow Analysis (IDX)

Composed answer to "who is moving this stock" — foreign net flow,
top broker net buyers/sellers, insider transactions, holder-composition
changes.

## When to Use

- "aliran dana BBRI seminggu terakhir"
- "smart money di TLKM"
- "siapa yang beli ASII kemarin"
- "% asing di BBCA sekarang"
- "ada insider di GOTO bulan ini?"

## Flow

1. Resolve symbol → uppercase bare code.
2. Parallel calls:
   - `finance.get_foreign_flow(symbol)`
   - `finance.get_broker_flow_aggregate(symbol, days=5)`
   - `finance.get_insider_trades(symbol, days=30)`
   - `finance.get_ownership_breakdown(symbol)`
   - `finance.get_major_holder_changes(symbol, days=30)`
3. Compose narrative sections:
   - **Foreign flow** — 1d net + trend.
   - **Broker leaders** — top 3 net buyers, top 3 net sellers by value.
   - **Insider** — last 3 transactions; flag director/commissioner.
   - **Ownership** — foreign vs domestic %, delta if `holder_changes` non-empty.
4. End with `retrieved_at` per section (from provenance).

## Rules

- Never invent broker codes or names — only surface what tools return.
- If ownership is unavailable (KSEI blocked), say so and continue with
  other sections. Never substitute other data.
- Numbers stay in IDR (raw), format with `,` thousands separator.
- If insider `side` is unclear, say "unclassified" — do not guess.
