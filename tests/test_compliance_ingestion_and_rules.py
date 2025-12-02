from io import BytesIO
from textwrap import dedent

from backend.accounting_store import save_books_tax, save_tax_returns
from backend.compliance_ingestion import parse_books_tax_csv, parse_returns_csv
from backend.compliance_rules import run_compliance_rules
from backend.db import init_db


def make_bytes(s: str) -> BytesIO:
    return BytesIO(dedent(s).lstrip().encode("utf-8"))


def test_compliance_rules_cover_all_three_cases():
    init_db()
    engagement_id = "eng-comp-1"

    returns_csv = make_bytes(
        """period,tax_type,turnover_return,tax_paid,filing_date,due_date
        2024-04,GST,100000,18000,2024-05-25,2024-05-20
        2024-05,GST,100000,500,2024-06-15,2024-06-20
        """
    )

    books_csv = make_bytes(
        """period,tax_type,turnover_books
        2024-04,GST,120000
        2024-05,GST,100000
        """
    )

    returns_rows = parse_returns_csv(returns_csv)
    books_rows = parse_books_tax_csv(books_csv)

    save_tax_returns(engagement_id, returns_rows)
    save_books_tax(engagement_id, books_rows)

    findings = run_compliance_rules(engagement_id)
    codes = {f.code for f in findings}

    assert "COMPLIANCE_UNRECONCILED_TURNOVER" in codes
    assert "COMPLIANCE_LATE_FILING" in codes
    assert "COMPLIANCE_EFFECTIVE_TAX_RATE_OUT_OF_BAND" in codes
