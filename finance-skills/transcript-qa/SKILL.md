---
name: transcript-qa
description: What management actually said, from public-expose decks. Use when user says "kata manajemen", "paparan publik", "public expose", "management said", "guidance manajemen".
version: 0.1.0
author: Finance Hermes
license: AGPL-3.0-only
platforms: [macos, linux]
metadata:
  hermes:
    tags: [Finance, IDX, Transcripts]
    related_skills: [stock-analysis, fundamental-analysis, catalyst-analysis]
    requires_tools:
      - finance.search_transcript
      - finance.transcript_coverage
      - finance.get_earnings_transcript
      - finance.transcript_ingest_once
---

# Transcript Q&A

Answer questions about management commentary using ONLY indexed public-expose
decks. Every claim carries a page number and a source URL, or it is not made.

## When to Use

- "apa kata manajemen BBRI soal NPL?"
- "guidance dividen BBCA di paparan publik terakhir"
- "what did management say about capex?"

## Flow

1. **Check coverage first** with `transcript_coverage(symbol)`. If `count` is
   0, say plainly that nothing is indexed for that issuer and offer
   `transcript_ingest_once`. Do not answer from training data — that is the
   whole failure this skill exists to prevent.

2. **Search** with `search_transcript(symbol, query)`. Use the user's own
   terminology: this is lexical search, so "NPL" finds more than "asset
   quality" if the deck says NPL.

3. **Answer with citations.** Every statement about what management said gets
   `(page N, <url>)`. Quote the wording; do not smooth it into your own voice.

4. **If nothing matches**, say so and show what the deck does cover. A miss is
   information — it may mean management did not address it.

## Rules

- **No citation, no claim.** If `hits` is empty you have nothing to report.
  Never bridge a gap with what you know about the company.
- The text is extracted from a PDF and is often a slide fragment, not prose.
  Present it as such. Do not invent connective sentences that imply management
  said something they only listed as a bullet.
- A deck with `pages_with_text: 0` was scanned images — say the file could not
  be read rather than reporting it as empty of content.
- Slides are management's own framing, produced to persuade. Tag per SOUL.md:
  `[FACT]` for the quote, `[ANALYSIS]` for your reading, `[RISK]` for what the
  deck does not address.
- Never present a deck as audited financials. It is a presentation.
