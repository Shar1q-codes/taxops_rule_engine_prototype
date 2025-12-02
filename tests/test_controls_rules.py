from datetime import date, datetime

from backend.db import init_db
from backend.accounting_store import save_gl_entries
from backend.accounting_models import GLEntry
from backend.controls_rules import run_controls_rules


def test_controls_rules_cover_core_scenarios():
    init_db()
    engagement_id = "eng-ctrl-1"
    today = date(2024, 4, 20)

    entries = [
        GLEntry(
            id="gl-1",
            account="100000",
            date=today,
            amount=1500.0,
            debit=1500.0,
            credit=0,
            description="Manual JE",
            user_id="u1",
            approved_by="u1",
            posted_at=datetime(2024, 4, 21, 10, 0),
            approved_at=datetime(2024, 4, 21, 11, 0),
            source="MANUAL",
        ),
        GLEntry(
            id="gl-2",
            account="200000",
            date=date(2024, 3, 1),
            amount=500.0,
            debit=500.0,
            credit=0,
            description="Backdated JE",
            user_id="u2",
            approved_by="u3",
            posted_at=datetime(2024, 4, 20, 12, 0),
            approved_at=datetime(2024, 4, 20, 13, 0),
            source="MANUAL",
        ),
        GLEntry(
            id="gl-3",
            account="999999",
            date=today,
            amount=5000.0,
            debit=5000.0,
            credit=0,
            description="Restricted posting",
            user_id="u5",
            approved_by="u6",
            posted_at=datetime(2024, 4, 20, 14, 0),
            approved_at=datetime(2024, 4, 20, 15, 0),
            source="MANUAL",
        ),
    ]

    for i in range(60):
        entries.append(
            GLEntry(
                id=f"gl-u4-{i}",
                account="300000",
                date=today,
                amount=100.0,
                debit=100.0,
                credit=0,
                description="Manual batch",
                user_id="u4",
                approved_by="u7",
                posted_at=datetime(2024, 4, 20, 9, 0),
                approved_at=datetime(2024, 4, 20, 9, 30),
                source="MANUAL",
            )
        )

    save_gl_entries(engagement_id, entries)
    findings = run_controls_rules(engagement_id)
    codes = {f.code for f in findings}

    assert "CONTROL_SAME_USER_CREATES_AND_APPROVES" in codes
    assert "CONTROL_BACKDATED_JOURNAL" in codes
    assert "CONTROL_MANUAL_JOURNAL_CONCENTRATION" in codes
    assert "CONTROL_POSTING_TO_RESTRICTED_ACCOUNTS" in codes
