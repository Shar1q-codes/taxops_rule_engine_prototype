from __future__ import annotations

from collections import Counter
from datetime import timedelta
from decimal import Decimal
from typing import List, Set

from .accounting_store import get_gl_entries
from .domain_rules import DomainFinding, make_finding_id

MATERIAL_THRESHOLD = Decimal("1000")
BACKDATE_TOLERANCE_DAYS = 7
MANUAL_CONCENTRATION_THRESHOLD = 50
RESTRICTED_ACCOUNTS: Set[str] = {
    "999999",
    "900000",
}


def run_controls_rules(engagement_id: str) -> List[DomainFinding]:
    entries = get_gl_entries(engagement_id)
    findings: List[DomainFinding] = []
    idx = 0

    # Same user creates and approves manual journals
    for e in entries:
        if (e.source or "").upper() != "MANUAL":
            continue
        if not e.user_id or not e.approved_by:
            continue
        if e.user_id == e.approved_by:
            findings.append(
                DomainFinding(
                    id=make_finding_id("controls", "CONTROL_SAME_USER_CREATES_AND_APPROVES", idx),
                    engagement_id=engagement_id,
                    domain="controls",
                    severity="high",
                    code="CONTROL_SAME_USER_CREATES_AND_APPROVES",
                    message="Manual journal created and approved by the same user.",
                    metadata={
                        "user_id": e.user_id,
                        "account": getattr(e, "account", None),
                        "date": str(getattr(e, "date", "")),
                        "amount": str(getattr(e, "amount", "")),
                    },
                )
            )
            idx += 1

    # Back-dated postings
    for e in entries:
        if not e.posted_at or not getattr(e, "date", None):
            continue
        delta = e.posted_at.date() - e.date
        if delta > timedelta(days=BACKDATE_TOLERANCE_DAYS):
            findings.append(
                DomainFinding(
                    id=make_finding_id("controls", "CONTROL_BACKDATED_JOURNAL", idx),
                    engagement_id=engagement_id,
                    domain="controls",
                    severity="medium",
                    code="CONTROL_BACKDATED_JOURNAL",
                    message="Journal appears to be back-dated relative to posting timestamp.",
                    metadata={
                        "user_id": e.user_id,
                        "account": getattr(e, "account", None),
                        "journal_date": str(e.date),
                        "posted_at": str(e.posted_at),
                        "days_difference": delta.days,
                    },
                )
            )
            idx += 1

    # Manual journal concentration per user
    manual_counts: Counter[str] = Counter()
    for e in entries:
        if (e.source or "").upper() == "MANUAL" and e.user_id:
            manual_counts[e.user_id] += 1

    for user_id, count in manual_counts.items():
        if count > MANUAL_CONCENTRATION_THRESHOLD:
            findings.append(
                DomainFinding(
                    id=make_finding_id("controls", "CONTROL_MANUAL_JOURNAL_CONCENTRATION", idx),
                    engagement_id=engagement_id,
                    domain="controls",
                    severity="medium",
                    code="CONTROL_MANUAL_JOURNAL_CONCENTRATION",
                    message="User has a high concentration of manual journal postings.",
                    metadata={
                        "user_id": user_id,
                        "manual_count": count,
                        "threshold": MANUAL_CONCENTRATION_THRESHOLD,
                    },
                )
            )
            idx += 1

    # Postings to restricted accounts
    for e in entries:
        account = getattr(e, "account", None)
        if not account:
            continue
        if account in RESTRICTED_ACCOUNTS:
            amount = getattr(e, "amount", None)
            if amount is None:
                continue
            if Decimal(str(amount)).copy_abs() < MATERIAL_THRESHOLD:
                continue
            findings.append(
                DomainFinding(
                    id=make_finding_id("controls", "CONTROL_POSTING_TO_RESTRICTED_ACCOUNTS", idx),
                    engagement_id=engagement_id,
                    domain="controls",
                    severity="high",
                    code="CONTROL_POSTING_TO_RESTRICTED_ACCOUNTS",
                    message="Material posting made to a restricted/system-only account.",
                    metadata={
                        "account": account,
                        "amount": str(amount),
                        "user_id": e.user_id,
                        "date": str(getattr(e, "date", "")),
                    },
                )
            )
            idx += 1

    return findings
