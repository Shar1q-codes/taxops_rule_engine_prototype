from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Optional, Tuple

from .accounting_store import get_bank_entries
from .db_models import DocumentORM
from .domain_rules import DomainLiteral

AMOUNT_TOLERANCE = Decimal("1")
DATE_TOLERANCE_DAYS = 7


def build_bank_entry_id(entry) -> str:
    account = getattr(entry, "account_number", None) or getattr(entry, "account", None) or "bank"
    return f"bank:{entry.id}:{account}:{entry.date}:{entry.amount}"


def match_document_to_bank_entries(
    engagement_id: str,
    doc: DocumentORM,
) -> Optional[Tuple[DomainLiteral, str]]:
    """
    Try to match a document to a single bank entry.

    Returns (domain, entry_id) or None if no reasonable match.
    For now, domain is always "bank" because we only match against bank entries.
    """
    entries = get_bank_entries(engagement_id)

    if not entries:
        return None

    candidates = []
    doc_amount = Decimal(str(doc.amount)) if doc.amount is not None else None
    for entry in entries:
        if doc_amount is None:
            continue
        diff = Decimal(str(entry.amount)) - doc_amount
        if diff.copy_abs() > AMOUNT_TOLERANCE:
            continue

        if doc.date and entry.date:
            delta = abs(entry.date - doc.date)
            if delta > timedelta(days=DATE_TOLERANCE_DAYS):
                continue

        score = diff.copy_abs()
        candidates.append((score, entry))

    if not candidates:
        return None

    candidates.sort(key=lambda t: t[0])
    _, best = candidates[0]

    entry_id = build_bank_entry_id(best)
    return "bank", entry_id
