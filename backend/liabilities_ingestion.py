from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from io import TextIOWrapper
from typing import BinaryIO, List

from backend.accounting_models import APEntry, LoanAccount, LoanPeriodEntry


def parse_loans_csv(file_obj: BinaryIO) -> List[LoanAccount]:
    wrapper = TextIOWrapper(file_obj, encoding="utf-8")
    reader = csv.DictReader(wrapper)
    loans: List[LoanAccount] = []
    for row in reader:
        if not row:
            continue
        maturity_raw = (row.get("maturity_date") or "").strip()
        maturity = datetime.strptime(maturity_raw, "%Y-%m-%d").date() if maturity_raw else None
        loans.append(
            LoanAccount(
                id=row["loan_id"].strip(),
                lender_name=row["lender_name"].strip(),
                opening_principal=Decimal(row["opening_principal"]),
                interest_rate_annual=Decimal(row["interest_rate_annual"]),
                start_date=datetime.strptime(row["start_date"].strip(), "%Y-%m-%d").date(),
                maturity_date=maturity,
            )
        )
    return loans


def parse_loan_periods_csv(file_obj: BinaryIO) -> List[LoanPeriodEntry]:
    wrapper = TextIOWrapper(file_obj, encoding="utf-8")
    reader = csv.DictReader(wrapper)
    periods: List[LoanPeriodEntry] = []
    for idx, row in enumerate(reader):
        if not row:
            continue
        periods.append(
            LoanPeriodEntry(
                id=row.get("entry_id") or f"loan-per-{idx}",
                loan_id=row["loan_id"].strip(),
                period_end=datetime.strptime(row["period_end"].strip(), "%Y-%m-%d").date(),
                opening_principal=Decimal(row["opening_principal"]),
                interest_expense=Decimal(row["interest_expense"]),
                principal_repayment=Decimal(row["principal_repayment"]),
                closing_principal=Decimal(row["closing_principal"]),
            )
        )
    return periods


def parse_ap_entries_csv(file_obj: BinaryIO) -> List[APEntry]:
    wrapper = TextIOWrapper(file_obj, encoding="utf-8")
    reader = csv.DictReader(wrapper)
    entries: List[APEntry] = []
    for idx, row in enumerate(reader):
        if not row:
            continue
        paid_raw = str(row.get("paid", "false")).strip().lower()
        paid = paid_raw in {"1", "true", "yes", "y"}
        payment_raw = (row.get("payment_date") or "").strip()
        payment_date = datetime.strptime(payment_raw, "%Y-%m-%d").date() if payment_raw else None
        entries.append(
            APEntry(
                id=row.get("entry_id") or f"ap-{idx}",
                vendor_id=row["vendor_id"].strip(),
                vendor_name=row["vendor_name"].strip(),
                invoice_id=row["invoice_id"].strip(),
                due_date=datetime.strptime(row["due_date"].strip(), "%Y-%m-%d").date(),
                amount=Decimal(row["amount"]),
                paid=paid,
                payment_date=payment_date,
            )
        )
    return entries
