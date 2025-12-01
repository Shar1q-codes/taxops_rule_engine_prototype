from __future__ import annotations

from typing import Dict, List, Tuple

from backend.accounting_store import get_transactions, get_trial_balance
from backend.domain_rules import DomainFinding, make_finding_id


def run_income_rules(engagement_id: str) -> List[DomainFinding]:
    txns = get_transactions(engagement_id)
    tb = get_trial_balance(engagement_id)
    findings: List[DomainFinding] = []

    income_account_codes = {
        row.account_code for row in tb if getattr(row, "type", None) == "income"
    } or {row.account_code for row in tb if "revenue" in row.account_name.lower()}

    duplicates_keyed: Dict[Tuple, List] = {}
    for txn in txns:
        for line in txn.lines:
            if line.account_code not in income_account_codes:
                continue
            key = (txn.date, txn.description.strip().lower(), line.debit, line.credit)
            duplicates_keyed.setdefault(key, []).append((txn, line))

    idx = 0
    for _, items in duplicates_keyed.items():
        if len(items) > 1:
            for txn, line in items:
                findings.append(
                    DomainFinding(
                        id=make_finding_id("income", "INCOME_DUPLICATE_DESC_AMOUNT", idx),
                        engagement_id=engagement_id,
                        domain="income",
                        severity="medium",
                        code="INCOME_DUPLICATE_DESC_AMOUNT",
                        message="Potential duplicate income transaction with same description and amount.",
                        account_code=line.account_code,
                        transaction_id=txn.id,
                        metadata={"date": str(txn.date), "description": txn.description},
                    )
                )
                idx += 1

    return findings
