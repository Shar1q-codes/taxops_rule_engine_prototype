from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from io import TextIOWrapper
from typing import BinaryIO, List

from backend.accounting_models import PayrollEmployee, PayrollEntry


def parse_payroll_employee_csv(file_obj: BinaryIO) -> List[PayrollEmployee]:
    wrapper = TextIOWrapper(file_obj, encoding="utf-8")
    reader = csv.DictReader(wrapper)
    employees: List[PayrollEmployee] = []
    for idx, row in enumerate(reader):
        if not row:
            continue
        employees.append(
            PayrollEmployee(
                id=row["employee_id"].strip(),
                name=row["name"].strip(),
                bank_account=(row.get("bank_account") or "").strip() or None,
                department=(row.get("department") or "").strip() or None,
                active=str(row.get("active", "true")).strip().lower() in {"1", "true", "yes", "y"},
            )
        )
    return employees


def parse_payroll_entries_csv(file_obj: BinaryIO) -> List[PayrollEntry]:
    wrapper = TextIOWrapper(file_obj, encoding="utf-8")
    reader = csv.DictReader(wrapper)
    entries: List[PayrollEntry] = []
    for idx, row in enumerate(reader):
        if not row:
            continue
        period = datetime.strptime(row["period"].strip(), "%Y-%m-%d").date()
        entries.append(
            PayrollEntry(
                id=row.get("entry_id") or f"pay-{idx}",
                employee_id=row["employee_id"].strip(),
                period=period,
                gross_pay=Decimal(row["gross_pay"]),
                net_pay=Decimal(row["net_pay"]),
                bank_account=(row.get("bank_account") or "").strip() or None,
                remarks=(row.get("remarks") or "").strip() or None,
            )
        )
    return entries
