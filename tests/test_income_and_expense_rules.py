from datetime import date
from decimal import Decimal

from backend.accounting_models import Transaction, TransactionLine, TrialBalanceRow
from backend.accounting_store import clear_engagement, save_transactions, save_trial_balance
from backend.income_rules import run_income_rules
from backend.expense_rules import run_expense_rules, POLICY_BREACH_THRESHOLD


def test_income_and_expense_rules_detect_findings():
    engagement_id = "eng-income-expense"
    clear_engagement(engagement_id)

    save_trial_balance(
        engagement_id,
        [
            TrialBalanceRow(
                account_code="4000",
                account_name="Revenue",
                opening_balance=Decimal("0"),
                debit=Decimal("0"),
                credit=Decimal("0"),
                closing_balance=Decimal("0"),
            ),
            TrialBalanceRow(
                account_code="6000",
                account_name="Office Expense",
                opening_balance=Decimal("0"),
                debit=Decimal("0"),
                credit=Decimal("0"),
                closing_balance=Decimal("0"),
            ),
        ],
    )

    save_transactions(
        engagement_id,
        [
            Transaction(
                id="t1",
                date=date(2024, 1, 10),
                description="Service revenue",
                lines=[
                    TransactionLine(account_code="4000", debit=Decimal("0"), credit=Decimal("500")),
                    TransactionLine(account_code="1000", debit=Decimal("500"), credit=Decimal("0")),
                ],
            ),
            Transaction(
                id="t2",
                date=date(2024, 1, 10),
                description="Service revenue",
                lines=[
                    TransactionLine(account_code="4000", debit=Decimal("0"), credit=Decimal("500")),
                    TransactionLine(account_code="1000", debit=Decimal("500"), credit=Decimal("0")),
                ],
            ),
            Transaction(
                id="t3",
                date=date(2024, 1, 15),
                description="Large equipment spend",
                lines=[
                    TransactionLine(account_code="6000", debit=POLICY_BREACH_THRESHOLD + 1, credit=Decimal("0")),
                    TransactionLine(account_code="2000", debit=Decimal("0"), credit=POLICY_BREACH_THRESHOLD + 1),
                ],
            ),
        ],
    )

    income_findings = run_income_rules(engagement_id)
    expense_findings = run_expense_rules(engagement_id)

    income_codes = {f.code for f in income_findings}
    expense_codes = {f.code for f in expense_findings}

    assert "INCOME_DUPLICATE_DESC_AMOUNT" in income_codes
    assert "EXP_DUPLICATE_EXPENSE_DESC_AMOUNT" not in expense_codes  # no duplicate expense
    assert "EXP_POLICY_BREACH_AMOUNT" in expense_codes
