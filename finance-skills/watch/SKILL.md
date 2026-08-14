---
name: watch
description: Manage price/flow/sentiment alerts. Use when user says "kabari kalau", "alert me when", "watch", "pantau", "notify".
version: 0.1.0
author: Finance Hermes
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, Alert, Watch]
    related_skills: [morning-digest, news-brief]
    requires_tools:
      - finance.watch_add
      - finance.watch_list
      - finance.watch_pause
      - finance.watch_resume
      - finance.watch_delete
      - finance.watch_evaluate_once
---

# Watch — alert rules

Turn a natural-language alert request into a persisted rule, then let the
evaluator (cron) fire it via Telegram when the metric crosses threshold.

## When to Use

- "kabari kalau BBCA turun >2% hari ini"
- "alert me when BTC drops 5%"
- "pantau volume TLKM >2x rata-rata"
- "watch sentimen BBRI"
- "notify BI Rate change"

## Flow

1. Parse the request into a `Rule` via `finance.watch_add(nl=...)`. The
   tool returns `{parsed: {...}, saved: false, id: null}` — the parsed
   rule for confirmation.
2. Echo the parsed rule to the user in plain language. Ask "confirm?"
3. On yes → call `finance.watch_add(nl=..., confirm=true)`; on edits →
   pass explicit fields (`symbol`, `metric`, `op`, `threshold`).
4. On success reply with the rule id, cooldown, and how to disable.

## Listing / editing

- `finance.watch_list()` returns all rules; render as a compact table
  (`id | symbol | metric | op | threshold | disabled`).
- `finance.watch_pause(id)` / `watch_resume(id)` toggle `disabled`.
- `finance.watch_delete(id)` removes the rule.

## Metrics allowlist

`price_change_pct_intraday`, `price_change_pct_1d|5d|20d`,
`volume_vs_ma20`, `foreign_net_flow_idr`, `bi_rate_change_bps`,
`sentiment_spike`, `macro_release:<indicator>`.

## Rules

- NEVER fabricate a rule id.
- NEVER call `watch_add(confirm=true)` without user confirmation.
- If the parser cannot resolve a symbol, ask explicitly rather than
  guessing.
- Multi-condition ("A OR B") not supported v1 → split into two rules
  and tell the user.
