from __future__ import annotations

from datetime import time
from decimal import Decimal
from typing import List, Set, Tuple

from backend.accounting_store import get_bank_entries, get_transactions
from backend.domain_rules import DomainFinding, make_finding_id

LATE_NIGHT_START = time(22, 0)
LATE_NIGHT_END = time(5, 0)
LARGE_AMOUNT_THRESHOLD = Decimal("100000")


def run_bank_rules(engagement_id: str) -> List[DomainFinding]:
    entries = get_bank_entries(engagement_id)
    txns = get_transactions(engagement_id)
    findings: List[DomainFinding] = []
    idx = 0

    gl_index: Set[Tuple] = set()
    for txn in txns:
        for line in txn.lines:
            gl_index.add((txn.date, txn.description.strip().lower(), line.debit - line.credit))

    for e in entries:
        key = (e.date, e.description.strip().lower(), e.amount)
        if key not in gl_index:
            findings.append(
                DomainFinding(
                    id=make_finding_id("bank", "BANK_UNMATCHED_ENTRY", idx),
                    engagement_id=engagement_id,
                    domain="bank",
                    severity="medium",
                    code="BANK_UNMATCHED_ENTRY",
                    message="Bank entry not matched to any GL transaction (prototype match on date/description/amount).",
                    metadata={"date": str(e.date), "description": e.description, "amount": str(e.amount)},
                )
            )
            idx += 1

    for e in entries:
        if e.balance is not None and e.balance < 0:
            findings.append(
                DomainFinding(
                    id=make_finding_id("bank", "BANK_NEGATIVE_BALANCE", idx),
                    engagement_id=engagement_id,
                    domain="bank",
                    severity="high",
                    code="BANK_NEGATIVE_BALANCE",
                    message="Bank balance is negative for this entry.",
                    metadata={"date": str(e.date), "balance": str(e.balance)},
                )
            )
            idx += 1

    for e in entries:
        if e.time is None:
            continue
        is_late = e.time >= LATE_NIGHT_START or e.time <= LATE_NIGHT_END
        if is_late and abs(e.amount) >= LARGE_AMOUNT_THRESHOLD:
            findings.append(
                DomainFinding(
                    id=make_finding_id("bank", "BANK_LATE_NIGHT_LARGE_TXN", idx),
                    engagement_id=engagement_id,
                    domain="bank",
                    severity="high",
                    code="BANK_LATE_NIGHT_LARGE_TXN",
                    message="Large late-night bank transaction detected.",
                    metadata={"date": str(e.date), "time": e.time.isoformat(), "amount": str(e.amount)},
                )
            )
            idx += 1

    round_entries = [e for e in entries if e.amount % Decimal("1000") == 0]
    if len(round_entries) >= 10:
        findings.append(
            DomainFinding(
                id=make_finding_id("bank", "BANK_FREQUENT_ROUND_FIGURES", idx),
                engagement_id=engagement_id,
                domain="bank",
                severity="medium",
                code="BANK_FREQUENT_ROUND_FIGURES",
                message="Frequent round-figure bank entries detected; review for possible structuring or manual adjustments.",
                metadata={"count": len(round_entries)},
            )
        )

    return findings
