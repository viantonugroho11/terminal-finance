---
name: morning-digest
description: Composed pre-market digest — IHSG, US overnight, FX, BI Rate, IDX movers, foreign flow, watchlist. Use when user asks "morning digest", "pagi", "recap", or when cron fires.
version: 0.1.0
author: Finance Hermes
license: AGPL-3.0-only
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, Digest, Daily]
    related_skills: [watch, market-overview]
    requires_tools:
      - finance.morning_digest
---

# Morning Digest

One structured, deterministic message summarising the pre-open landscape
for Indonesian-market users.

## When to Use

- User asks: "morning digest", "recap pagi", "kondisi market", "kabar pagi"
- Cron (via Hermes `cron_jobs`) at 07:30 WIB weekdays.

## Flow

1. Call `finance.morning_digest(lang=?)` — `lang` defaults to
   `DIGEST_LANG` env (`id` or `en`).
2. The tool returns pre-rendered Markdown ≤4096 chars ready for
   Telegram; forward verbatim.

## Rules

- NEVER paraphrase or reorder digest sections — output is deterministic
  by contract.
- NEVER inject speculation. If a section is empty, leave it out.
- If the tool returns `error`, forward the error line and do not
  hallucinate numbers.
