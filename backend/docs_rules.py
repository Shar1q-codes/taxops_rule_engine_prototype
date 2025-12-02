from __future__ import annotations

from decimal import Decimal
from typing import List

from sqlalchemy.orm import Session

from .db_models import DocumentLinkORM
from .domain_rules import DomainFinding, make_finding_id
from .accounting_store import get_bank_entries
from .docs_matching import build_bank_entry_id

MATERIAL_THRESHOLD = Decimal("1000")


def run_document_rules(db: Session, engagement_id: str) -> List[DomainFinding]:
    findings: List[DomainFinding] = []
    idx = 0

    bank_entries = get_bank_entries(engagement_id)
    linked_entry_ids = {
        link.entry_id
        for link in db.query(DocumentLinkORM)
        .filter(DocumentLinkORM.engagement_id == engagement_id)
        .all()
    }

    for entry in bank_entries:
        amount = Decimal(str(entry.amount))
        if amount.copy_abs() <= MATERIAL_THRESHOLD:
            continue

        entry_id = build_bank_entry_id(entry)
        if entry_id in linked_entry_ids:
            continue

        findings.append(
            DomainFinding(
                id=make_finding_id("documents", "DOC_MISSING_SUPPORTING_DOCUMENT", idx),
                engagement_id=engagement_id,
                domain="documents",
                severity="high",
                code="DOC_MISSING_SUPPORTING_DOCUMENT",
                message="Material bank entry has no linked supporting document.",
                metadata={
                    "account": getattr(entry, "account_number", None) or getattr(entry, "account", None),
                    "date": str(entry.date),
                    "amount": str(entry.amount),
                    "entry_id": entry_id,
                },
            )
        )
        idx += 1

    return findings
