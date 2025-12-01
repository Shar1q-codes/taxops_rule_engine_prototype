import io
from datetime import date, time
from decimal import Decimal

from backend.accounting_models import Transaction, TransactionLine
from backend.accounting_store import clear_engagement, save_transactions, save_bank_entries
from backend.bank_ingestion import parse_bank_csv
from backend.bank_rules import run_bank_rules, LARGE_AMOUNT_THRESHOLD
from backend.domain_rules import DomainFinding


def test_bank_ingestion_and_rules():
    engagement_id = "eng-bank"
    clear_engagement(engagement_id)

    csv_body = "\n".join(
        [
            "date,description,amount,balance,time,account_number,reference",
            "2024-01-05,Paycheck,1500,5000,09:00,1111,ref1",
            "05/01/2024,ATM Withdrawal,-200,4800,23:30,1111,ref2",
            "2024-01-06,Vendor Payment,-50000,-100,10:00,1111,ref3",
            "2024-01-07,Large Night Wire,-150000,100000,23:45,1111,ref4",
        ]
    )
    entries = parse_bank_csv(io.BytesIO(csv_body.encode("utf-8")))
    save_bank_entries(engagement_id, entries)

    save_transactions(
        engagement_id,
        [
            Transaction(
                id="gl1",
                date=date(2024, 1, 5),
                description="Paycheck",
                lines=[
                    TransactionLine(account_code="4000", debit=Decimal("0"), credit=Decimal("-1500")),
                ],
            )
        ],
    )

    # Add round-figure entries to trigger the heuristic.
    round_entries = [f"2024-02-{i:02d},Round {i},1000,,22:00,1111," for i in range(1, 11)]
    extra_csv = "\n".join(["date,description,amount,balance,time,account_number,reference"] + round_entries)
    extra_entries = parse_bank_csv(io.BytesIO(extra_csv.encode("utf-8")))
    save_bank_entries(engagement_id, entries + extra_entries)

    findings = run_bank_rules(engagement_id)
    codes = {f.code for f in findings}
    assert "BANK_UNMATCHED_ENTRY" in codes
    assert "BANK_NEGATIVE_BALANCE" in codes
    assert "BANK_LATE_NIGHT_LARGE_TXN" in codes
    assert "BANK_FREQUENT_ROUND_FIGURES" in codes

    large_txn = next(f for f in findings if f.code == "BANK_LATE_NIGHT_LARGE_TXN")
    assert Decimal(large_txn.metadata["amount"]) <= Decimal(f"-{LARGE_AMOUNT_THRESHOLD}")
