# ADR-0024: IDX earnings-call transcript ingest + Q&A skill

- Status: Proposed (spec written, not implemented — see `docs/specs/0024-earnings-transcript-qa.md`)
- Date: 2026-08-14
- Deciders: Finance Terminal team

## Context

IDX-listed issuers publish quarterly public expose + earnings call materials via IR pages, IDXChannel, and KSEI (PDF slides, occasional MP3/MP4). No open API. Bloomberg/Refinitiv cover this but paywalled. Retail + independent analysts read PDFs by hand.

Terminal already ingests filings for US via SEC EDGAR (ADR-0018). No parallel for IDX narrative disclosures. Users ask "apa kata manajemen BBRI soal NPL Q3" and get numeric fundamentals only — no management commentary.

## Decision

New provider `IdxTranscriptProvider` + new capability `earnings_transcript`. Pipeline:

1. Nightly ingest cron: crawl issuer IR pages (`.co.id/investor-relations`) for new PDF disclosures. Deduplicate by SHA256.
2. Parse PDF → text via `pdfplumber`. Chunk 800 tokens, overlap 100.
3. Embed with local `bge-m3` (multilingual, fits Indonesian) → SQLite FTS5 + vector column (`sqlite-vss`).
4. New MCP tools: `get_earnings_transcript(symbol, period)` returns metadata + full text; `search_transcript(symbol, query, top_k)` returns ranked chunks with page cite.
5. New skill `earnings-qa` composes: retrieve top-k chunks → DeepSeek answers with mandatory chunk citation.

Storage: `~/.hermes/finance/transcripts/{symbol}/{period}.pdf` + `transcripts.db`. Provenance carries source URL + retrieval date + PDF page.

## Consequences

- Positive: fills real gap in Indonesian equity research. Cites page number — auditable.
- Positive: reuses provenance + skill patterns; no Hermes fork.
- Negative: PDF scraping brittle per issuer template; ingest breakage silent unless monitored. Mitigation: coverage report tool `transcript_coverage(symbol)` shows last-seen date per ticker.
- Negative: local embedding adds ~500MB model + first-run cost. Acceptable for research workstation; not for edge.
- Negative: legal — public IR PDFs are freely distributable but bulk redistribution may violate ToS on some issuer sites. Skill runs local, does not re-host.
- Follow-ups: initial coverage list (LQ45 first), monitoring alert on ingest failure, RUNBOOK entry for re-embed after model bump.

## Alternatives considered

- **Manual upload only.** Rejected: kills the "ask any listed issuer" pitch.
- **OpenAI embeddings.** Rejected: cost + data-residency; local bge-m3 competitive on Indonesian.
- **Full audio transcription (Whisper).** Deferred: PDF slides cover 80% of Q&A content; audio adds cost + latency without proportional signal. Revisit if issuers stop publishing slides.
- **Store in Postgres + pgvector.** Rejected v1: SQLite fits single-tenant, no ops burden.

## References

- ADR-0018 (SEC filings) — parallel pattern for US.
- ADR-0020 (Indonesian providers).
- ADR-0011 (provenance).
