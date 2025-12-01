import io
from decimal import Decimal

from backend.accounting_store import clear_engagement, save_ap_entries, save_loan_periods, save_loans
from backend.liabilities_ingestion import parse_ap_entries_csv, parse_loan_periods_csv, parse_loans_csv
from backend.liabilities_rules import run_liabilities_rules, INTEREST_TOLERANCE


def test_liabilities_ingestion_and_rules():
    engagement_id = "eng-liabilities"
    clear_engagement(engagement_id)

    loans_csv = "\n".join(
        [
            "loan_id,lender_name,opening_principal,interest_rate_annual,start_date,maturity_date",
            "L1,Bank A,100000,0.10,2024-01-01,2025-01-01",
        ]
    )
    periods_csv = "\n".join(
        [
            "entry_id,loan_id,period_end,opening_principal,interest_expense,principal_repayment,closing_principal",
            "P1,L1,2024-02-29,100000,10000,5000,95000",  # implied 10% OK
            "P2,L1,2024-03-31,95000,25000,0,95000",  # implied high -> should flag
        ]
    )
    ap_csv = "\n".join(
        [
            "entry_id,vendor_id,vendor_name,invoice_id,due_date,amount,paid,payment_date",
            "AP1,V1,Vendor One,INV1,2024-01-15,-500,false,",  # negative balance driver
            "AP2,V1,Vendor One,INV2,2024-01-10,100,false,",  # still net negative
            "AP3,V2,Vendor Two,INV3,2023-12-31,1000,false,",  # overdue
        ]
    )

    loans = parse_loans_csv(io.BytesIO(loans_csv.encode("utf-8")))
    periods = parse_loan_periods_csv(io.BytesIO(periods_csv.encode("utf-8")))
    ap_entries = parse_ap_entries_csv(io.BytesIO(ap_csv.encode("utf-8")))

    save_loans(engagement_id, loans)
    save_loan_periods(engagement_id, periods)
    save_ap_entries(engagement_id, ap_entries)

    findings = run_liabilities_rules(engagement_id)
    codes = {f.code for f in findings}

    assert "LIAB_INTEREST_VS_BALANCE_UNREASONABLE" in codes
    assert "LIAB_NEGATIVE_VENDOR_BALANCE" in codes
    assert "LIAB_OVERDUE_LIABILITIES" in codes

    interest = next(f for f in findings if f.code == "LIAB_INTEREST_VS_BALANCE_UNREASONABLE")
    implied = Decimal(interest.metadata["implied_rate"])
    assert implied - Decimal("0.10") > INTEREST_TOLERANCE
