---
name: screener
description: Find stocks matching numeric criteria. Use when user says "cari saham", "screening", "screen", "filter saham", "bank dengan PBV di bawah", "which stocks have".
version: 0.1.0
author: Finance Hermes
license: AGPL-3.0-only
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, Screener, IDX]
    related_skills: [stock-analysis, fundamental-analysis, peer-analysis]
    requires_tools:
      - finance.screen_stocks
      - finance.screener_fields
---

# Screener

Turn a plain-language screen into filters, confirm them, then run it.
Every number shown comes from `screen_stocks` — never from your own knowledge.

## When to Use

- "cari bank IDX PBV di bawah 1.5 dan ROE di atas 15%"
- "saham dividen tinggi di atas 5%"
- "which IDX banks trade below book value?"

## Flow

1. **Parse** the request into filters: `{field, op, value}`.
   - Percentages become fractions: "ROE di atas 15%" → `{"field": "roe", "op": ">", "value": 0.15}`.
   - "di bawah book value" → `{"field": "pbv", "op": "<", "value": 1.0}`.
   - Sector words ("bank", "perbankan") → `{"field": "sector", "op": "=", "value": "Financials"}`.
   - If unsure which field a phrase means, call `screener_fields` and pick from the list.

2. **Echo and confirm.** Show the parsed filters in one short line before running:
   > Filter: PBV < 1.5, ROE > 15%, sektor Financials. Lanjut?

   Do this because a misparsed filter produces a confident, wrong list.

3. **Run** `screen_stocks(filters=..., order_by=..., limit=...)`.

4. **Present** a compact table: symbol, name, and only the columns that were
   filtered or sorted on. State `snapshot_date` — the data is a daily
   snapshot, not live.

5. **Explain** the top 3 briefly: what stands out, and one risk each.

## Rules

- If `count` is 0, say so and suggest loosening a specific filter. Do not
  widen the screen yourself and present the result as if it were asked for.
- If the reply carries `reason: no_snapshot_yet`, say the snapshot has not run
  yet and offer `screener_snapshot_once`. Do not fall back to guessing.
- On `SCREENER_FIELD_UNKNOWN`, the error lists the valid fields. Re-map and
  retry once, then ask.
- A screen is a starting list, never a recommendation. Tag output per SOUL.md:
  `[FACT]` for the numbers, `[ANALYSIS]` for the reading, `[RISK]` for what
  the filters hide — a low PBV may be low for a reason the screen cannot see.
- Never present a screen as complete coverage: it reflects one snapshot of the
  configured universe (IDX), not every listed company everywhere.
