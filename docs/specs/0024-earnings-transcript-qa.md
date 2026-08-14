# Spec: IDX earnings transcript ingest + Q&A

Ref: ADR-0024.

## Goal

Ask any listed IDX issuer about management commentary; get answer with PDF page citation.

## User stories

- Analyst: "Apa kata manajemen BBRI soal NPL di public expose Q3 2026?" → answer + link to page 14 of PDF.
- Analyst: `transcript_coverage BBCA` → last 8 quarters available, next expected date.

## Success conditions

- `pytest finance-mcp/tests/test_transcripts.py` green: ingest, dedup, chunk, retrieve.
- End-to-end: for LQ45 tickers, ≥90% have ≥1 transcript in last 2 quarters.
- Answer always cites page + source URL; no citation → skill refuses.

## Deliverables

### 1. Provider `IdxTranscriptProvider`

Path: `finance-mcp/finance_mcp/providers/idx_transcript.py`.

Config: `finance-mcp/finance_mcp/data/ir_sources.yaml` — one entry per issuer:
```yaml
BBRI:
  ir_url: https://ir.bri.co.id/investor-relations/financial-information
  pdf_pattern: "Public Expose|Analyst Meeting"
```

Methods:
- `list_transcripts(symbol) -> list[TranscriptMeta]`
- `fetch_pdf(url) -> bytes`

### 2. Ingest pipeline

Path: `finance-mcp/finance_mcp/ingest/transcripts.py`.

Cron: `0 3 * * *` (03:00 WIB nightly).

Steps:
1. For each configured symbol, `list_transcripts` → new URLs (compare against DB).
2. Fetch PDF, SHA256 dedup, save to `~/.hermes/finance/transcripts/{symbol}/{sha}.pdf`.
3. `pdfplumber` extract per-page text.
4. Chunk 800 tokens, overlap 100, tag with `(symbol, period, page)`.
5. Embed with `bge-m3` local (`sentence-transformers`).
6. Insert into SQLite: `transcripts(id, symbol, period, url, sha, published_at)` + `chunks(id, transcript_id, page, text, embedding BLOB)`.

### 3. MCP tools

- `get_earnings_transcript(symbol, period="latest") -> {url, published_at, pages: int, text}`
- `search_transcript(symbol, query, top_k=5) -> [{chunk, page, score}]`
- `transcript_coverage(symbol) -> {periods: [...], last_ingest: ts, next_expected: date}`

All return provenance `{source: "issuer_ir", url, retrieved_at, sha}`.

### 4. Skill `earnings-qa`

Path: `finance-skills/earnings-qa/SKILL.md`.

Flow: parse question → identify symbol + period → `search_transcript` → LLM synthesize with **mandatory** `[p.14]` inline citations. Refuse if top score <threshold.

### 5. Ops

- Ingest failure metric per symbol; alert if >3 consecutive failures.
- RUNBOOK: "Re-embed after model bump" — bumping `bge-m3` version invalidates embeddings; script `scripts/reembed_transcripts.py` provided.

## Out of scope

- Audio transcription (deferred).
- Non-Indonesian issuers (US covered by SEC via ADR-0018).

## Milestones

1. IR source config + list_transcripts for 5 pilot symbols (BBCA, BBRI, TLKM, ASII, GOTO) (1d).
2. PDF fetch + parse + chunk + dedup (1d).
3. Embedding + SQLite store + retrieval (1d).
4. MCP tools + provenance (0.5d).
5. `earnings-qa` skill + citation enforcement + tests (1d).
6. Expand config to LQ45 + coverage report (0.5d).

Total: ~5d.
