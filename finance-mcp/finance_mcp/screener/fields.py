"""The screener's field allowlist — its security boundary.

Filters reach this module having been parsed out of natural language by an
LLM, which means field names are attacker-influenceable in exactly the way a
query string is. Nothing here is ever interpolated into SQL from caller input:
a name is looked up in FIELDS, and only the column this module owns is used.

Adding a field means adding an entry here. There is deliberately no escape
hatch for "just pass the column through".
"""
from __future__ import annotations

from dataclasses import dataclass

from ..errors import ErrorCode, FinanceError


@dataclass(frozen=True)
class Field:
    column: str          # physical column; never comes from caller input
    label: str           # what a human calls it
    numeric: bool = True


FIELDS: dict[str, Field] = {
    # Identity / classification
    "market":            Field("market", "market", numeric=False),
    "sector":            Field("sector", "sector", numeric=False),
    "industry":          Field("industry", "industry", numeric=False),
    # Price + size
    "price":             Field("price", "last price"),
    "market_cap":        Field("market_cap", "market capitalisation"),
    "mcap":              Field("market_cap", "market capitalisation"),
    # Valuation
    "pe":                Field("pe_ratio", "P/E"),
    "pe_ratio":          Field("pe_ratio", "P/E"),
    "forward_pe":        Field("forward_pe", "forward P/E"),
    "peg":               Field("peg_ratio", "PEG"),
    "pbv":               Field("price_to_book", "P/BV"),
    "price_to_book":     Field("price_to_book", "P/BV"),
    "price_to_sales":    Field("price_to_sales", "P/S"),
    # Profitability
    "roe":               Field("return_on_equity", "ROE"),
    "return_on_equity":  Field("return_on_equity", "ROE"),
    "roa":               Field("return_on_assets", "ROA"),
    "profit_margin":     Field("profit_margin", "net margin"),
    "operating_margin":  Field("operating_margin", "operating margin"),
    # Growth
    "revenue_growth":    Field("revenue_growth", "revenue growth"),
    "earnings_growth":   Field("earnings_growth", "earnings growth"),
    # Balance sheet / cash
    "debt_to_equity":    Field("debt_to_equity", "debt/equity"),
    "current_ratio":     Field("current_ratio", "current ratio"),
    "free_cashflow":     Field("free_cashflow", "free cash flow"),
    # Income to holder
    "dividend_yield":    Field("dividend_yield", "dividend yield"),
    "div_yield":         Field("dividend_yield", "dividend yield"),
    "beta":              Field("beta", "beta"),
    # Banking-specific (ADR-0020) — nullable for non-banks, which is what
    # makes "cari bank IDX PBV<1.5, ROE>15%" answerable beyond the basics.
    "nim":               Field("net_interest_margin", "net interest margin"),
    "npl":               Field("non_performing_loan_ratio", "NPL ratio"),
    "car":               Field("capital_adequacy_ratio", "CAR"),
    "ldr":               Field("loan_to_deposit_ratio", "LDR"),
    "casa":              Field("casa_ratio", "CASA ratio"),
    "loan_growth":       Field("loan_growth", "loan growth"),
    "deposit_growth":    Field("deposit_growth", "deposit growth"),
}

OPS = {"<", "<=", ">", ">=", "=", "!=", "in"}


def resolve(name: str) -> Field:
    """Look up a caller-supplied field name, or refuse it."""
    key = (name or "").strip().lower()
    f = FIELDS.get(key)
    if f is None:
        raise FinanceError(
            ErrorCode.SCREENER_FIELD_UNKNOWN,
            f"unknown screener field {name!r}",
            details={"known_fields": sorted(FIELDS)},
        )
    return f


def resolve_op(op: str) -> str:
    """Operators are matched against a fixed set, never passed through."""
    o = (op or "").strip().lower()
    if o not in OPS:
        raise FinanceError(
            ErrorCode.SCREENER_FIELD_UNKNOWN,
            f"unsupported screener operator {op!r}",
            details={"known_ops": sorted(OPS)},
        )
    return o
