from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Dict, List, Tuple

from backend.accounting_store import get_books_tax, get_tax_returns
from backend.domain_rules import DomainFinding, make_finding_id

MATERIALITY_PCT = Decimal("0.01")
TAX_RATE_BANDS: Dict[str, Tuple[Decimal, Decimal]] = {
    "GST": (Decimal("0.04"), Decimal("0.22")),
    "VAT": (Decimal("0.04"), Decimal("0.25")),
    "TDS": (Decimal("0.01"), Decimal("0.20")),
    "IT": (Decimal("0.02"), Decimal("0.40")),
}


def run_compliance_rules(engagement_id: str) -> List[DomainFinding]:
    returns = get_tax_returns(engagement_id)
    books = get_books_tax(engagement_id)

    findings: List[DomainFinding] = []
    idx = 0

    books_map: Dict[Tuple[str, str], Decimal] = {}
    for b in books:
        key = (b.period, b.tax_type.upper())
        books_map[key] = books_map.get(key, Decimal("0")) + b.turnover_books

    for r in returns:
        key = (r.period, r.tax_type.upper())
        books_turnover = books_map.get(key, Decimal("0"))
        if r.turnover_return == 0:
            continue
        diff = books_turnover - r.turnover_return
        materiality = (r.turnover_return * MATERIALITY_PCT).copy_abs()
        if diff.copy_abs() > materiality:
            findings.append(
                DomainFinding(
                    id=make_finding_id("compliance", "COMPLIANCE_UNRECONCILED_TURNOVER", idx),
                    engagement_id=engagement_id,
                    domain="compliance",
                    severity="high",
                    code="COMPLIANCE_UNRECONCILED_TURNOVER",
                    message="Books turnover does not reconcile to tax return turnover for this period and tax type.",
                    metadata={
                        "period": r.period,
                        "tax_type": r.tax_type,
                        "turnover_return": str(r.turnover_return),
                        "turnover_books": str(books_turnover),
                        "difference": str(diff),
                    },
                )
            )
            idx += 1

    for r in returns:
        if r.filing_date > r.due_date:
            findings.append(
                DomainFinding(
                    id=make_finding_id("compliance", "COMPLIANCE_LATE_FILING", idx),
                    engagement_id=engagement_id,
                    domain="compliance",
                    severity="medium",
                    code="COMPLIANCE_LATE_FILING",
                    message="Return appears to be filed after the statutory due date.",
                    metadata={
                        "period": r.period,
                        "tax_type": r.tax_type,
                        "filing_date": str(r.filing_date),
                        "due_date": str(r.due_date),
                    },
                )
            )
            idx += 1

    for r in returns:
        if r.turnover_return <= 0 or r.tax_paid <= 0:
            continue
        eff_rate = (r.tax_paid / r.turnover_return).quantize(Decimal("0.0001"))
        band = TAX_RATE_BANDS.get(r.tax_type.upper())
        if not band:
            continue
        low, high = band
        if eff_rate < low or eff_rate > high:
            findings.append(
                DomainFinding(
                    id=make_finding_id("compliance", "COMPLIANCE_EFFECTIVE_TAX_RATE_OUT_OF_BAND", idx),
                    engagement_id=engagement_id,
                    domain="compliance",
                    severity="medium",
                    code="COMPLIANCE_EFFECTIVE_TAX_RATE_OUT_OF_BAND",
                    message="Effective tax rate falls outside expected band for this tax type.",
                    metadata={
                        "period": r.period,
                        "tax_type": r.tax_type,
                        "turnover_return": str(r.turnover_return),
                        "tax_paid": str(r.tax_paid),
                        "effective_rate": str(eff_rate),
                        "expected_low": str(low),
                        "expected_high": str(high),
                    },
                )
            )
            idx += 1

    return findings
