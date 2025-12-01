from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from backend.accounting_store import get_transactions, get_trial_balance


class BookFinding(BaseModel):
    id: str
    engagement_id: str
    severity: Literal["low", "medium", "high", "critical"]
    code: str
    message: str
    account_code: Optional[str] = None
    transaction_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


RESTRICTED_ACCOUNT_CODES = {"9999", "9998"}


def run_books_rules(engagement_id: str) -> List[BookFinding]:
    tb_rows = get_trial_balance(engagement_id)
    transactions = get_transactions(engagement_id)
    findings: List[BookFinding] = []

    suspense_codes = set(RESTRICTED_ACCOUNT_CODES)
    suspense_codes.update({row.account_code for row in tb_rows if "suspense" in row.account_name.lower()})

    for row in tb_rows:
        if row.account_code in suspense_codes and row.closing_balance != Decimal("0"):
            findings.append(
                BookFinding(
                    id=f"{engagement_id}-suspense-{row.account_code}",
                    engagement_id=engagement_id,
                    severity="high",
                    code="BOOKS_SUSPENSE_BALANCE",
                    message=f"Suspense/provisional account {row.account_code} has non-zero closing balance of {row.closing_balance}.",
                    account_code=row.account_code,
                    metadata={
                        "closing_balance": str(row.closing_balance),
                        "account_name": row.account_name,
                    },
                )
            )

    for txn in transactions:
        for line in txn.lines:
            if line.account_code in suspense_codes:
                findings.append(
                    BookFinding(
                        id=f"{engagement_id}-restricted-{txn.id}-{line.account_code}",
                        engagement_id=engagement_id,
                        severity="medium",
                        code="BOOKS_RESTRICTED_ACCOUNT_USAGE",
                        message=f"Transaction {txn.id} hits restricted account {line.account_code}.",
                        account_code=line.account_code,
                        transaction_id=txn.id,
                    )
                )

    if transactions:
        oldest = min(txn.date for txn in transactions)
        if oldest and oldest < date.today().replace(month=1, day=1):
            findings.append(
                BookFinding(
                    id=f"{engagement_id}-prior-period",
                    engagement_id=engagement_id,
                    severity="low",
                    code="BOOKS_PRIOR_PERIOD_ACTIVITY",
                    message="Ledger contains potential prior-period activity; review for adjustments.",
                    transaction_id=next((txn.id for txn in transactions if txn.date == oldest), None),
                    metadata={"oldest_transaction_date": oldest.isoformat()},
                )
            )
    return findings
