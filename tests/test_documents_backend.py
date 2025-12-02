from datetime import date
from decimal import Decimal

from backend.db import SessionLocal, init_db
from backend.db_models import DocumentLinkORM, DocumentORM
from backend.accounting_store import save_bank_entries
from backend.accounting_models import BankEntry
from backend.docs_matching import build_bank_entry_id, match_document_to_bank_entries
from backend.docs_rules import run_document_rules


def test_match_document_to_bank_entry_and_missing_doc_rule():
    init_db()
    engagement_id = "doc-eng-101"

    bank_entries = [
        BankEntry(
            id="be-1",
            account_number="001",
            date=date(2024, 4, 15),
            amount=Decimal("1500.0"),
            description="Vendor payment",
        ),
        BankEntry(
            id="be-2",
            account_number="001",
            date=date(2024, 4, 16),
            amount=Decimal("100.0"),
            description="Small fee",
        ),
    ]
    save_bank_entries(engagement_id, bank_entries)

    with SessionLocal() as db:
        db.query(DocumentLinkORM).delete()
        db.query(DocumentORM).delete()
        db.commit()

        doc = DocumentORM(
            engagement_id=engagement_id,
            filename="inv1.pdf",
            content=b"dummy",
            type="INVOICE",
            amount=1500.0,
            date=date(2024, 4, 15),
            counterparty="Vendor",
            external_ref="INV-001",
        )
        db.add(doc)
        db.flush()

        domain_entry = match_document_to_bank_entries(engagement_id, doc)
        assert domain_entry is not None
        domain, entry_id = domain_entry
        assert domain == "bank"
        assert entry_id == build_bank_entry_id(bank_entries[0])

        link = DocumentLinkORM(
            engagement_id=engagement_id,
            domain=domain,
            entry_id=entry_id,
            doc_id=doc.id,
        )
        db.add(link)
        db.commit()

        findings = run_document_rules(db, engagement_id)
        codes = {f.code for f in findings}
        assert "DOC_MISSING_SUPPORTING_DOCUMENT" not in codes

        db.query(DocumentLinkORM).delete()
        db.commit()
        findings2 = run_document_rules(db, engagement_id)
        codes2 = {f.code for f in findings2}
        assert "DOC_MISSING_SUPPORTING_DOCUMENT" in codes2
