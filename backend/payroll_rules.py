from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Dict, List, Tuple

from backend.accounting_store import get_payroll_employees, get_payroll_entries
from backend.domain_rules import DomainFinding, make_finding_id


def run_payroll_rules(engagement_id: str) -> List[DomainFinding]:
    employees = get_payroll_employees(engagement_id)
    entries = get_payroll_entries(engagement_id)
    findings: List[DomainFinding] = []
    idx = 0

    employees_by_id: Dict[str, str] = {e.id: e.name for e in employees}
    employees_by_bank: Dict[str, List[str]] = defaultdict(list)
    for emp in employees:
        if emp.bank_account:
            employees_by_bank[emp.bank_account].append(emp.id)

    for entry in entries:
        if entry.employee_id not in employees_by_id:
            findings.append(
                DomainFinding(
                    id=make_finding_id("payroll", "PAYROLL_GHOST_EMPLOYEE", idx),
                    engagement_id=engagement_id,
                    domain="payroll",
                    severity="high",
                    code="PAYROLL_GHOST_EMPLOYEE",
                    message="Payroll entry for employee not present in employee master.",
                    metadata={"employee_id": entry.employee_id, "period": str(entry.period), "gross_pay": str(entry.gross_pay)},
                )
            )
            idx += 1

    for bank_account, emp_ids in employees_by_bank.items():
        if len(emp_ids) > 1:
            findings.append(
                DomainFinding(
                    id=make_finding_id("payroll", "PAYROLL_SHARED_BANK_ACCOUNT", idx),
                    engagement_id=engagement_id,
                    domain="payroll",
                    severity="medium",
                    code="PAYROLL_SHARED_BANK_ACCOUNT",
                    message="Multiple employees share the same bank account.",
                    metadata={"bank_account": bank_account, "employee_ids": emp_ids},
                )
            )
            idx += 1

    history: Dict[str, List[Tuple[date, Decimal]]] = defaultdict(list)
    for entry in entries:
        history[entry.employee_id].append((entry.period, entry.net_pay))

    for emp_id, records in history.items():
        records.sort(key=lambda x: x[0])
        if len(records) < 2:
            continue
        for i in range(1, len(records)):
            prev_period, prev_pay = records[i - 1]
            curr_period, curr_pay = records[i]
            if prev_pay <= 0:
                continue
            if curr_pay >= prev_pay * Decimal("1.5"):
                findings.append(
                    DomainFinding(
                        id=make_finding_id("payroll", "PAYROLL_ABNORMAL_INCREMENT", idx),
                        engagement_id=engagement_id,
                        domain="payroll",
                        severity="medium",
                        code="PAYROLL_ABNORMAL_INCREMENT",
                        message="Net pay increased abnormally vs prior period for this employee.",
                        metadata={
                            "employee_id": emp_id,
                            "previous_period": str(prev_period),
                            "previous_net_pay": str(prev_pay),
                            "current_period": str(curr_period),
                            "current_net_pay": str(curr_pay),
                        },
                    )
                )
                idx += 1

    return findings
