from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Tuple

from backend.accounting_store import get_transactions, get_trial_balance
from backend.domain_rules import DomainFinding, make_finding_id

POLICY_BREACH_THRESHOLD = Decimal("10000")


def run_expense_rules(engagement_id: str) -> List[DomainFinding]:
    txns = get_transactions(engagement_id)
    tb = get_trial_balance(engagement_id)
    findings: List[DomainFinding] = []

    expense_account_codes = {
        row.account_code for row in tb if getattr(row, "type", None) == "expense"
    } or {row.account_code for row in tb if "expense" in row.account_name.lower()}

    dup_keyed: Dict[Tuple, List] = {}
    for txn in txns:
        for line in txn.lines:
            if line.account_code not in expense_account_codes:
                continue
            key = (txn.date, txn.description.strip().lower(), line.debit, line.credit)
            dup_keyed.setdefault(key, []).append((txn, line))
    idx = 0
    for _, items in dup_keyed.items():
        if len(items) > 1:
            for txn, line in items:
                findings.append(
                    DomainFinding(
                        id=make_finding_id("expense", "EXP_DUPLICATE_EXPENSE_DESC_AMOUNT", idx),
                        engagement_id=engagement_id,
                        domain="expense",
                        severity="medium",
                        code="EXP_DUPLICATE_EXPENSE_DESC_AMOUNT",
                        message="Potential duplicate expense with same description and amount.",
                        account_code=line.account_code,
                        transaction_id=txn.id,
                        metadata={"date": str(txn.date), "description": txn.description},
                    )
                )
                idx += 1

    for txn in txns:
        for line in txn.lines:
            if line.account_code not in expense_account_codes:
                continue
            amount = line.debit if line.debit > 0 else line.credit
            if amount >= POLICY_BREACH_THRESHOLD:
                findings.append(
                    DomainFinding(
                        id=make_finding_id("expense", "EXP_POLICY_BREACH_AMOUNT", idx),
                        engagement_id=engagement_id,
                        domain="expense",
                        severity="high",
                        code="EXP_POLICY_BREACH_AMOUNT",
                        message=f"Expense line exceeds policy threshold of {POLICY_BREACH_THRESHOLD}.",
                        account_code=line.account_code,
                        transaction_id=txn.id,
                        metadata={"amount": str(amount), "description": txn.description},
                    )
                )
                idx += 1

    return findings
