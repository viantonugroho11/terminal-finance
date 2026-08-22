---
name: peer-analysis
description: Sector peers + comps table. Use for "peers of X", "who competes with X", "how does X compare to peers", "bandingkan X dengan sektornya".
version: 0.1.0
author: Finance Hermes
license: AGPL-3.0-only
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, Equity, Peers, Comps]
    related_skills: [stock-analysis, equity-research]
    requires_tools:
      - finance.get_sector_info
      - finance.get_company_profile
      - finance.get_fundamentals
      - finance.search_stocks
      - finance.get_quote
---

# Peer Analysis

Comps table across a hand-picked or sector-derived peer set. Never
invent tickers.

## When to Use

- "peers of NVDA", "how does BBCA compare to other banks"
- "sector comps", "bandingkan BBCA dan BBRI dan BMRI dan BBNI"

## Procedure

1. Establish peer set:
   - If user names peers explicitly (e.g. "BBCA vs BBRI vs BMRI"), use those.
   - Else `finance.get_sector_info(<SYM>)` and `finance.search_stocks(<sector name>)` to build a candidate list of 3–8 tickers in the same sector.

2. For each peer in parallel:
   - `finance.get_quote(<peer>)`
   - `finance.get_fundamentals(<peer>)`
   - `finance.get_company_profile(<peer>)` (for market cap)

3. Build a comps table normalized to the same schema.

## Output Format

```
<SYM> — Peer Comps ({sector})

Ticker   Name              MktCap    P/E    P/B    ROE    OpMgn   RevGrw   DivYld
------------------------------------------------------------------------------------
<SYM>    <name>            $X.XB     X.XX   X.XX   XX%    XX%     XX%      X.X%
<PEER>   <name>            $X.XB     X.XX   X.XX   XX%    XX%     XX%      X.X%
...

MEDIAN                     —         X.XX   X.XX   XX%    XX%     XX%      X.X%

INTERPRETATION [ANALYSIS]
  vs Median:
    · P/E:   +/- X.XX (premium / discount)
    · P/B:   +/- X.XX
    · ROE:   +/- XX pp (higher/lower profitability)
    · OpMgn: +/- XX pp
    · RevGrw: +/- XX pp

  Positioning read: <cheap-with-low-quality? premium-with-high-quality? etc>

STRENGTHS vs PEERS [ANALYSIS]
  · <specific — cite the metric>
WEAKNESSES vs PEERS [ANALYSIS]
  · <specific>

RISKS [RISK]
  · Premium valuation vs peers on X — mean-reversion risk
  · Below-peer growth on Y — market-share loss risk

CONFIDENCE
  Low if: peer set <3, or resolver market varies across peers
  High if: 5+ peers, same sector, same market
```

## Rules

- Peer set MUST be homogeneous by market (do not mix IDX + US peers unless the user explicitly asked for a global comp).
- If a peer's `get_fundamentals` returns null for a metric, print "n/a" in its cell — do not median-impute.
- Median row: skip nulls in the calc (do not treat null as 0).
- Currency: mix warning — if peers report in different currencies, add a note. Do NOT convert.
- For banks: swap the row header to include NIM/NPL/CAR and drop OpMgn/RevGrw when the banking ratios are available.
- Never invent a peer. If `search_stocks` returns few, cap the table there and note "peer universe thin".
