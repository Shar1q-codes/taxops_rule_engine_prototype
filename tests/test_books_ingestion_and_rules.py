import os
from datetime import date
from decimal import Decimal

os.environ["AUTH_BYPASS"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from backend import app as app_module  # noqa: E402
from backend.accounting_models import Transaction, TransactionLine, TrialBalanceRow  # noqa: E402
from backend.accounting_store import clear_engagement, get_trial_balance, save_transactions, save_trial_balance  # noqa: E402
from backend.books_rules import run_books_rules  # noqa: E402

client = TestClient(app_module.app)
AUTH_HEADER = {"Authorization": "Bearer test"}


def test_trial_balance_ingestion_from_csv():
    engagement_id = "eng-books-tb"
    clear_engagement(engagement_id)
    csv_body = "\n".join(
        [
            "account_code,account_name,opening_balance,debit,credit,closing_balance",
            "1000,Cash,0,100,0,100",
            "9999,Suspense,0,0,50,-50",
        ]
    )
    resp = client.post(f"/api/books/{engagement_id}/trial-balance", files={"file": ("tb.csv", csv_body, "text/csv")}, headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["rows_ingested"] == 2
    stored = get_trial_balance(engagement_id)
    assert len(stored) == 2
    assert stored[0].account_code == "1000"


def test_gl_ingestion_from_json_grouped_by_txn():
    engagement_id = "eng-books-gl"
    clear_engagement(engagement_id)
    payload = [
        {"txn_id": "t1", "date": "2024-01-05", "description": "Sale", "account_code": "4000", "debit": "0", "credit": "150"},
        {"txn_id": "t1", "date": "2024-01-05", "description": "Sale", "account_code": "1100", "debit": "150", "credit": "0"},
        {"txn_id": "t2", "date": "2024-01-06", "description": "Cash receipt", "account_code": "1000", "debit": "150", "credit": "0"},
    ]
    resp = client.post(f"/api/books/{engagement_id}/gl", json=payload, headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["transactions_ingested"] == 2
    assert Decimal(str(data["total_debit"])) == Decimal("300")
    assert Decimal(str(data["total_credit"])) == Decimal("150")


def test_books_rules_detect_suspense_and_restricted_accounts():
    engagement_id = "eng-books-rules"
    clear_engagement(engagement_id)
    save_trial_balance(
        engagement_id,
        [
            TrialBalanceRow(
                account_code="9999",
                account_name="Suspense",
                opening_balance=Decimal("0"),
                debit=Decimal("0"),
                credit=Decimal("0"),
                closing_balance=Decimal("25"),
            )
        ],
    )
    save_transactions(
        engagement_id,
        [
            Transaction(
                id="txn-prior",
                date=date.today().replace(year=date.today().year - 1, month=12, day=31),
                description="Prior period adjustment",
                lines=[TransactionLine(account_code="9999", debit=Decimal("0"), credit=Decimal("25"))],
            )
        ],
    )
    findings = run_books_rules(engagement_id)
    codes = {f.code for f in findings}
    assert "BOOKS_SUSPENSE_BALANCE" in codes
    assert "BOOKS_RESTRICTED_ACCOUNT_USAGE" in codes
    assert "BOOKS_PRIOR_PERIOD_ACTIVITY" in codes
