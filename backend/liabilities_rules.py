from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Dict, List, Tuple

from backend.accounting_store import get_ap_entries, get_loan_periods, get_loans
from backend.domain_rules import DomainFinding, make_finding_id

INTEREST_TOLERANCE = Decimal("0.03")


def run_liabilities_rules(engagement_id: str) -> List[DomainFinding]:
    loans = get_loans(engagement_id)
    periods = get_loan_periods(engagement_id)
    ap_entries = get_ap_entries(engagement_id)
    findings: List[DomainFinding] = []
    idx = 0

    loans_by_id: Dict[str, Tuple[Decimal, Decimal]] = {
        loan.id: (loan.opening_principal, loan.interest_rate_annual) for loan in loans
    }

    for per in periods:
        if per.loan_id not in loans_by_id:
            continue
        _, rate = loans_by_id[per.loan_id]
        if per.opening_principal <= 0:
            continue
        implied_rate = per.interest_expense / per.opening_principal
        if implied_rate < 0:
            continue
        delta = abs(implied_rate - rate)
        if delta > INTEREST_TOLERANCE:
            findings.append(
                DomainFinding(
                    id=make_finding_id("liabilities", "LIAB_INTEREST_VS_BALANCE_UNREASONABLE", idx),
                    engagement_id=engagement_id,
                    domain="liabilities",
                    severity="medium",
                    code="LIAB_INTEREST_VS_BALANCE_UNREASONABLE",
                    message="Interest expense appears inconsistent with stated loan rate and opening principal.",
                    metadata={
                        "loan_id": per.loan_id,
                        "period_end": str(per.period_end),
                        "opening_principal": str(per.opening_principal),
                        "interest_expense": str(per.interest_expense),
                        "stated_rate": str(rate),
                        "implied_rate": str(implied_rate),
                    },
                )
            )
            idx += 1

    ap_by_vendor: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    today = date.today()

    for entry in ap_entries:
        ap_by_vendor[entry.vendor_id] += entry.amount
        if not entry.paid and entry.due_date < today and entry.amount > 0:
            findings.append(
                DomainFinding(
                    id=make_finding_id("liabilities", "LIAB_OVERDUE_LIABILITIES", idx),
                    engagement_id=engagement_id,
                    domain="liabilities",
                    severity="high",
                    code="LIAB_OVERDUE_LIABILITIES",
                    message="Overdue AP balance; invoice is past due and unpaid.",
                    metadata={
                        "vendor_id": entry.vendor_id,
                        "vendor_name": entry.vendor_name,
                        "invoice_id": entry.invoice_id,
                        "due_date": str(entry.due_date),
                        "amount": str(entry.amount),
                    },
                )
            )
            idx += 1

    for vendor_id, balance in ap_by_vendor.items():
        if balance < 0:
            findings.append(
                DomainFinding(
                    id=make_finding_id("liabilities", "LIAB_NEGATIVE_VENDOR_BALANCE", idx),
                    engagement_id=engagement_id,
                    domain="liabilities",
                    severity="medium",
                    code="LIAB_NEGATIVE_VENDOR_BALANCE",
                    message="Vendor has a negative net AP balance (potential credit/debit note mismatch).",
                    metadata={"vendor_id": vendor_id, "balance": str(balance)},
                )
            )
            idx += 1

    return findings
