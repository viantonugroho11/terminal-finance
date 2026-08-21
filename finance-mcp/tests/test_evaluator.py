"""Deterministic evaluator — ADR-0016."""
from finance_mcp.evaluator import (
    ACCEPT_THRESHOLD,
    RETRY_THRESHOLD,
    RUBRIC_WEIGHTS,
    evaluate,
)


def test_weights_sum_to_100():
    assert sum(RUBRIC_WEIGHTS.values()) == 100


_GOOD = """# BBCA — Bank Central Asia — Deep Research

## Snapshot [FACT]

- Price: 9,500 [^1]
- Market cap: Rp 1,200 T [^2]

## Business [FACT]

Bank swasta terbesar Indonesia. [^3]

## Fundamentals [FACT]

| Metric | Value |
|---|---|
| P/E | 22.1 [^4] |
| ROE | 21.3% [^4] |
| NIM | 5.7% [^4] |

## Valuation [FACT]

### Assumptions [ASSUMPTION]

- Discount rate: 10.0% [^6]

### Result [FACT]

- Enterprise value: Rp 1,300 T [^6]

### Sensitivity [FACT]

Grid rendered here. [^7]

## Technicals [FACT]

- RSI 14: 55.2 [^8]

## Bull Case [ANALYSIS]

- Strong NIM 5.7% vs peers [^4]
- CASA advantage supports funding cost [^4]

## Bear Case [ANALYSIS]

- Premium valuation P/E 22.1 vs sector [^4]
- Loan growth deceleration [^5]

## Risks [RISK]

- NPL uptick above 3% guideline [^5]
- BI-Rate cut compresses NIM [^9]

## Confidence [ANALYSIS]

**High** — 3+ years statements from primary source.

## Sources

[^1]: `finance.get_quote(BBCA)` — provider=idx, retrieved_at=2025-08-13, tier=scraped.
[^2]: `finance.get_company_profile(BBCA)` — provider=idx.
[^3]: `finance.get_company_profile(BBCA)` — provider=idx.
[^4]: `finance.get_fundamentals(BBCA)` — provider=idx, tier=scraped.
[^5]: `finance.get_financial_statements(BBCA)` — provider=idx.
[^6]: `finance.valuation_dcf(BBCA)` — deterministic.
[^7]: `finance.valuation_sensitivity(BBCA)` — deterministic.
[^8]: `finance.get_technical(BBCA)` — deterministic.
[^9]: `finance.get_macro(bi_rate)` — provider=bi, tier=primary.
"""


def test_good_report_accepts():
    r = evaluate(_GOOD, expected_symbol="BBCA")
    assert r.verdict == "accept", (r.score, [m.__dict__ for m in r.misses])
    assert r.score >= ACCEPT_THRESHOLD
    assert "citations_on_numeric_claims" in r.passes
    assert "template_conformance" in r.passes


def test_missing_sections_flagged():
    stripped = _GOOD.split("## Bull Case")[0] + _GOOD.split("## Sources")[0].split("## Bear Case")[0] + _GOOD[_GOOD.rfind("## Sources"):]
    r = evaluate(stripped, expected_symbol="BBCA")
    assert "template_conformance" not in r.passes
    assert any("missing sections" in m.detail for m in r.misses)


def test_dangling_citation_flagged():
    # Insert a body-only reference to id 42 that has no Sources entry.
    md = _GOOD.replace("## Confidence [ANALYSIS]",
                       "Also see [^42] for context.\n\n## Confidence [ANALYSIS]")
    r = evaluate(md, expected_symbol="BBCA")
    assert 42 in r.counters["dangling_citations"]


def test_hallucinated_ticker_flagged():
    md = _GOOD.replace("Strong NIM 5.7% vs peers",
                       "Beats peers XXXX and YYYY on NIM 5.7%")
    r = evaluate(md, expected_symbol="BBCA")
    orphans = set(r.counters["orphan_tickers"])
    assert "XXXX" in orphans and "YYYY" in orphans


def test_bull_bear_ungrounded_reduces_score():
    md = _GOOD.replace("[^4]", "").replace("[^5]", "")
    r = evaluate(md, expected_symbol="BBCA")
    assert "bull_and_bear_grounded" not in r.passes


def test_sensitivity_missing_flagged():
    md = _GOOD.replace("### Sensitivity [FACT]\n\nGrid rendered here. [^7]", "")
    r = evaluate(md, expected_symbol="BBCA")
    assert "sensitivity_present" not in r.passes


def test_empty_risks_flagged():
    md = _GOOD.replace(
        "## Risks [RISK]\n\n- NPL uptick above 3% guideline [^5]\n- BI-Rate cut compresses NIM [^9]",
        "## Risks [RISK]\n\n",
    )
    r = evaluate(md, expected_symbol="BBCA")
    assert "risks_grounded" not in r.passes


def test_confidence_missing_flagged():
    md = _GOOD.replace(
        "## Confidence [ANALYSIS]\n\n**High** — 3+ years statements from primary source.",
        "## Confidence [ANALYSIS]\n\n",
    )
    r = evaluate(md, expected_symbol="BBCA")
    assert "confidence_matches_evidence" not in r.passes


def test_low_quality_report_verdict_low_confidence():
    md = "# Some Report\n\nBuy NVDA at $500. Trust me.\n"
    r = evaluate(md, expected_symbol="NVDA")
    assert r.score < RETRY_THRESHOLD
    assert r.verdict == "low_confidence"


def test_result_to_dict_shape():
    d = evaluate(_GOOD, expected_symbol="BBCA").to_dict()
    assert set(d) == {"score", "verdict", "passes", "misses", "counters"}
    assert isinstance(d["misses"], list)
