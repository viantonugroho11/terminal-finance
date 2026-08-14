# Spec: Alert engine + morning digest

Ref: ADR-0023.

## Goal

Two skills that turn the terminal into a daily surface via Hermes cron + Telegram gateway.

## User stories

- As IDX retail user, I say "kabari kalau BBCA turun >2% intraday atau volume >2x MA20". Bot messages me on Telegram when trigger fires.
- As analyst, I get one Telegram message at 07:30 WIB every weekday with IHSG close, movers, foreign flow, US overnight, DXY, USDIDR, BI Rate, watchlist deltas.

## Success conditions

- `pytest finance-mcp/tests/test_watch.py` green: rule parse, evaluate, cooldown, dedup.
- `pytest finance-mcp/tests/test_digest.py` green: composition, i18n, char cap 4096.
- Live: registered watch fires within 60s of threshold breach during market hours; digest lands within 5min of scheduled time.
- No new MCP tool required — only new skills + rule store.

## Deliverables

### 1. Rule store

Path: `~/.hermes/finance/watches.jsonl`. Append-only.

Schema per line:
```json
{
  "id": "w_01H...",
  "created_at": "2026-08-14T02:30:00Z",
  "user": "default",
  "symbol": "BBCA",
  "metric": "price_change_pct_intraday",
  "op": ">",
  "threshold": -2.0,
  "window": null,
  "channel": "telegram:default",
  "cooldown_sec": 3600,
  "last_fired_at": null,
  "disabled": false
}
```

Allowed `metric`:
- `price_change_pct_intraday`
- `price_change_pct_1d|5d|20d`
- `volume_vs_ma20` (ratio)
- `foreign_net_flow_idr`
- `bi_rate_change_bps`
- `macro_release:<indicator>` (BPS CPI, GDP, etc.)

### 2. Evaluator

Module: `finance-skills/watch/evaluator.py`.

Cron: `*/1 9-16 * * 1-5` (WIB market hours), `*/15 * * * *` off-hours.

Loop:
1. Read `watches.jsonl`, skip disabled + within cooldown.
2. For each rule, resolve metric via existing MCP tool (`get_quote`, `get_foreign_flow`, `get_bi_rate`).
3. Compare against threshold; if match, fire via Telegram gateway.
4. Append `fire_event` to `watches.events.jsonl` (audit).
5. Update `last_fired_at` (compact rewrite when >10MB).

### 3. `watch` skill

Path: `finance-skills/watch/SKILL.md`.

NL → rule via DeepSeek. Two-step: parse → echo parsed rule → user confirms → persist.

Commands recognized: `watch`, `watches list`, `watch pause <id>`, `watch delete <id>`.

### 4. `morning-digest` skill

Path: `finance-skills/morning-digest/SKILL.md`.

Cron: `30 7 * * 1-5` (Asia/Jakarta).

Composition order (each is one existing tool call):
1. `get_market_overview(market="IDX")` — IHSG close, change, top 5 movers.
2. `get_foreign_flow` top 5 net inflow + top 5 outflow.
3. `get_market_overview(market="US")` — SPX, NDX overnight.
4. `get_quote(DXY)`, `get_quote(USDIDR=X)`.
5. `get_bi_rate()` + upcoming BPS/OJK release calendar (next 7d).
6. Watchlist deltas: for each symbol in `~/.hermes/finance/watchlist.txt`, quote + 1d change.

Template: `templates/digest_id.md`, `templates/digest_en.md`. Chose lang from env `DIGEST_LANG=id|en`.

Output ≤4096 chars (Telegram cap). Long sections truncated with "…lihat terminal".

### 5. Ops

- `RUNBOOKS.md` new section: "Managing watches" — inspect, edit, disable, purge.
- Metric: `watch_fires_total`, `digest_send_success_total`, exposed via existing observability.

## Out of scope

- Multi-user (see ADR-0030).
- Push from providers (all polling).
- Sub-minute latency.

## Milestones

1. Rule store schema + read/write + tests (0.5d).
2. Evaluator loop + metric adapters + tests (1d).
3. `watch` skill NL parse + confirmation flow (0.5d).
4. `morning-digest` skill composition + template + i18n (0.5d).
5. Cron registration + Telegram wire + smoke test (0.5d).

Total: ~3d.
