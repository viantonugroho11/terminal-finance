"""Deterministic report evaluator — ADR-0016 rubric.

Scores a Markdown research report (ADR-0019 format) against a fixed
rubric. Pure regex + citation-graph + numeric cross-reference; no LLM
call, no tool call, no I/O. Result is reproducible and auditable.

Score ≥ 80 = accept. 60 ≤ score < 80 = ask for retry with specific
misses. < 60 after retries = publish with [Low-Confidence] banner.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any


# Rubric weights (must sum to 100). Mirrors phase-f-multi-agent-plan.md.
RUBRIC_WEIGHTS: dict[str, int] = {
    "citations_on_numeric_claims": 25,
    "bull_and_bear_grounded":      15,
    "sensitivity_present":         10,
    "risks_grounded":              15,
    "no_hallucinated_tickers":     20,
    "template_conformance":        10,
    "confidence_matches_evidence":  5,
}

ACCEPT_THRESHOLD = 80
RETRY_THRESHOLD  = 60

# Required section headers per ADR-0019 template (level-2 `##`).
_REQUIRED_SECTIONS = (
    "Snapshot", "Business", "Fundamentals", "Valuation",
    "Bull Case", "Bear Case", "Risks", "Confidence", "Sources",
)

# Section tag suffixes we recognize.
_TAGS = ("[FACT]", "[ANALYSIS]", "[RISK]", "[ASSUMPTION]")

# Regexes.
_CITATION       = re.compile(r"\[\^(\d+)\]")
_SOURCE_ENTRY   = re.compile(r"^\[\^(\d+)\]:", re.MULTILINE)
_H2             = re.compile(r"^##\s+([A-Za-z][A-Za-z0-9 /&\-]+?)(?:\s+\[[A-Z ]+\])?\s*$",
                             re.MULTILINE)
_TICKER_TOKEN   = re.compile(r"\b([A-Z]{2,5})(?:\.JK)?\b")
_NUMERIC_INLINE = re.compile(
    r"(?<![A-Za-z\^\[\_\-])"           # not preceded by identifier chars
    r"(?:\$|Rp\s*)?"                    # optional currency
    r"-?\d+(?:[.,]\d+)?"                # the number
    r"(?:\s*(?:%|bps|B|M|K|T))?"       # optional unit
)


@dataclass
class RubricMiss:
    criterion: str
    weight: int
    detail: str
    line: int | None = None


@dataclass
class EvaluationResult:
    score: int                     # 0-100
    verdict: str                   # "accept" | "retry" | "low_confidence"
    passes: list[str] = field(default_factory=list)
    misses: list[RubricMiss] = field(default_factory=list)
    counters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "verdict": self.verdict,
            "passes": self.passes,
            "misses": [m.__dict__ for m in self.misses],
            "counters": self.counters,
        }


def _find_sections(md: str) -> dict[str, tuple[int, int]]:
    """Return {section_name: (start_line, end_line)} for level-2 headers."""
    positions: list[tuple[str, int]] = []
    for m in _H2.finditer(md):
        name = m.group(1).strip()
        line = md[:m.start()].count("\n") + 1
        positions.append((name, line))
    sections: dict[str, tuple[int, int]] = {}
    for i, (name, start) in enumerate(positions):
        end = positions[i + 1][1] - 1 if i + 1 < len(positions) else md.count("\n") + 1
        sections[name] = (start, end)
    return sections


def _section_body(md: str, name: str,
                  sections: dict[str, tuple[int, int]]) -> str:
    if name not in sections:
        return ""
    start, end = sections[name]
    lines = md.splitlines()
    return "\n".join(lines[start:end])


def _numeric_claims_without_citation(section_body: str) -> int:
    """Count numeric tokens on lines that carry no [^n] citation."""
    misses = 0
    for line in section_body.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("|--") \
           or s.startswith("```"):
            continue
        # Table headers / separators skipped.
        if _CITATION.search(s):
            continue
        # A line with numbers and no citation counts as one miss regardless
        # of how many numbers appear, to avoid inflating on wide tables.
        if _NUMERIC_INLINE.search(s):
            misses += 1
    return misses


def _extract_symbols(md: str) -> set[str]:
    tokens = set()
    for m in _TICKER_TOKEN.finditer(md):
        tok = m.group(1)
        # Filter obvious noise: single-letter, common English words, and
        # ADR/PDF/etc. token-like strings.
        if tok in {"USD", "IDR", "JPY", "HKD", "GBP", "CNY", "GDP", "CPI",
                   "BI", "OJK", "BPS", "EDGAR", "ADR", "MCP", "DCF", "WACC",
                   "CAPM", "PDF", "PT", "TBK", "URL", "NPL", "CAR", "NIM",
                   "LDR", "CASA", "ROE", "ROA", "PER", "PBV", "EPS", "FCF",
                   "IHSG", "ETF", "REIT", "IPO", "SEC", "SPI", "JISDOR",
                   "YOY", "QOQ", "TTM", "IFRS", "GAAP", "US", "ID", "HK",
                   "IDX", "BEI", "IHSG", "SPX", "ISO", "UTC", "JSON",
                   "YAML", "HTTP", "API"}:
            continue
        tokens.add(tok)
    return tokens


def _sources_registry(md: str) -> tuple[set[int], set[str]]:
    """Return (citation-ids defined in Sources, tickers named in Sources)."""
    sections = _find_sections(md)
    body = _section_body(md, "Sources", sections)
    ids = {int(m.group(1)) for m in _SOURCE_ENTRY.finditer(body)}
    tickers = _extract_symbols(body)
    return ids, tickers


def _cited_ids(md: str) -> set[int]:
    return {int(m.group(1)) for m in _CITATION.finditer(md)}


def _has_tag(section: str, tag: str) -> bool:
    return tag in section


def _confidence_matches(md: str, sections: dict[str, tuple[int, int]]) -> bool:
    body = _section_body(md, "Confidence", sections).lower()
    if not body:
        return False
    return any(w in body for w in ("low", "moderate", "high"))


def evaluate(md: str, *, expected_symbol: str | None = None) -> EvaluationResult:
    """Score a report and return a structured verdict."""
    sections = _find_sections(md)
    misses: list[RubricMiss] = []
    passes: list[str] = []
    score = 0
    counters: dict[str, Any] = {}

    # 1) citations_on_numeric_claims (25).
    fact_sections = ("Snapshot", "Fundamentals", "Financial Statements",
                     "Valuation", "Technicals", "Catalysts")
    uncited = 0
    for s in fact_sections:
        body = _section_body(md, s, sections)
        if body:
            uncited += _numeric_claims_without_citation(body)
    counters["uncited_numeric_lines"] = uncited
    w = RUBRIC_WEIGHTS["citations_on_numeric_claims"]
    if uncited == 0:
        score += w; passes.append("citations_on_numeric_claims")
    elif uncited <= 3:
        score += w // 2
        misses.append(RubricMiss("citations_on_numeric_claims", w // 2,
                                 f"{uncited} numeric line(s) missing [^n] citation"))
    else:
        misses.append(RubricMiss("citations_on_numeric_claims", w,
                                 f"{uncited} numeric line(s) missing [^n] citation"))

    # 2) bull_and_bear_grounded (15).
    bull_body = _section_body(md, "Bull Case", sections)
    bear_body = _section_body(md, "Bear Case", sections)
    bull_cited = len(_CITATION.findall(bull_body))
    bear_cited = len(_CITATION.findall(bear_body))
    counters["bull_citations"] = bull_cited
    counters["bear_citations"] = bear_cited
    w = RUBRIC_WEIGHTS["bull_and_bear_grounded"]
    if bull_cited >= 2 and bear_cited >= 2:
        score += w; passes.append("bull_and_bear_grounded")
    elif bull_cited >= 1 and bear_cited >= 1:
        score += w // 2
        misses.append(RubricMiss("bull_and_bear_grounded", w // 2,
                                 f"Bull cites={bull_cited}, Bear cites={bear_cited}; "
                                 "want ≥2 each"))
    else:
        misses.append(RubricMiss("bull_and_bear_grounded", w,
                                 f"Bull cites={bull_cited}, Bear cites={bear_cited}; "
                                 "at least one side ungrounded"))

    # 3) sensitivity_present (10).
    val_body = _section_body(md, "Valuation", sections)
    has_sensitivity = "Sensitivity" in val_body or "sensitivity" in val_body
    w = RUBRIC_WEIGHTS["sensitivity_present"]
    counters["has_sensitivity"] = has_sensitivity
    if has_sensitivity:
        score += w; passes.append("sensitivity_present")
    else:
        misses.append(RubricMiss("sensitivity_present", w,
                                 "Valuation section lacks a Sensitivity subblock"))

    # 4) risks_grounded (15).
    risks_body = _section_body(md, "Risks", sections)
    risk_lines = [ln for ln in risks_body.splitlines()
                  if ln.strip().startswith(("·", "-", "*"))]
    risks_with_metric = sum(1 for ln in risk_lines
                            if _NUMERIC_INLINE.search(ln) or _CITATION.search(ln))
    counters["risk_bullets"] = len(risk_lines)
    counters["risks_with_metric_or_citation"] = risks_with_metric
    w = RUBRIC_WEIGHTS["risks_grounded"]
    if risk_lines and risks_with_metric >= max(2, len(risk_lines) // 2):
        score += w; passes.append("risks_grounded")
    elif risk_lines:
        score += w // 2
        misses.append(RubricMiss("risks_grounded", w // 2,
                                 f"{risks_with_metric}/{len(risk_lines)} risks tied "
                                 "to a metric or citation"))
    else:
        misses.append(RubricMiss("risks_grounded", w,
                                 "Risks section empty"))

    # 5) no_hallucinated_tickers (20).
    body_tickers = _extract_symbols(md)
    _, sources_tickers = _sources_registry(md)
    # If a symbol is named in body but absent from Sources AND is not the
    # subject symbol, it's a hallucination candidate.
    subject = expected_symbol.upper() if expected_symbol else None
    orphan = {t for t in body_tickers
              if t not in sources_tickers and t != subject}
    counters["body_tickers"] = sorted(body_tickers)
    counters["orphan_tickers"] = sorted(orphan)
    w = RUBRIC_WEIGHTS["no_hallucinated_tickers"]
    if not orphan:
        score += w; passes.append("no_hallucinated_tickers")
    elif len(orphan) <= 2:
        score += w // 2
        misses.append(RubricMiss("no_hallucinated_tickers", w // 2,
                                 f"tickers in body not backed by Sources: "
                                 f"{sorted(orphan)}"))
    else:
        misses.append(RubricMiss("no_hallucinated_tickers", w,
                                 f"{len(orphan)} orphan tickers: {sorted(orphan)}"))

    # 6) template_conformance (10) — required sections present.
    missing_sections = [s for s in _REQUIRED_SECTIONS if s not in sections]
    counters["missing_sections"] = missing_sections
    # Also every citation must resolve.
    cited = _cited_ids(md)
    defined_ids, _ = _sources_registry(md)
    dangling = sorted(cited - defined_ids)
    counters["dangling_citations"] = dangling
    w = RUBRIC_WEIGHTS["template_conformance"]
    if not missing_sections and not dangling:
        score += w; passes.append("template_conformance")
    elif not missing_sections:
        score += w // 2
        misses.append(RubricMiss("template_conformance", w // 2,
                                 f"dangling citations: {dangling}"))
    else:
        misses.append(RubricMiss("template_conformance", w,
                                 f"missing sections {missing_sections}; "
                                 f"dangling citations {dangling}"))

    # 7) confidence_matches_evidence (5).
    w = RUBRIC_WEIGHTS["confidence_matches_evidence"]
    conf_present = _confidence_matches(md, sections)
    if conf_present:
        score += w; passes.append("confidence_matches_evidence")
    else:
        misses.append(RubricMiss("confidence_matches_evidence", w,
                                 "Confidence section missing or lacks a level word"))

    if score >= ACCEPT_THRESHOLD:
        verdict = "accept"
    elif score >= RETRY_THRESHOLD:
        verdict = "retry"
    else:
        verdict = "low_confidence"

    return EvaluationResult(score=score, verdict=verdict,
                            passes=passes, misses=misses, counters=counters)
