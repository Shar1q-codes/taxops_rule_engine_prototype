import io
from decimal import Decimal

from backend.accounting_store import clear_engagement, save_payroll_employees, save_payroll_entries
from backend.payroll_ingestion import parse_payroll_employee_csv, parse_payroll_entries_csv
from backend.payroll_rules import run_payroll_rules


def test_payroll_ingestion_and_rules():
    engagement_id = "eng-payroll"
    clear_engagement(engagement_id)

    employees_csv = "\n".join(
        [
            "employee_id,name,bank_account,department,active",
            "E1,Alice,ACC1,Finance,true",
            "E2,Bob,ACC1,Finance,true",
            "E3,Charlie,ACC2,Ops,true",
        ]
    )
    entries_csv = "\n".join(
        [
            "entry_id,employee_id,period,gross_pay,net_pay,bank_account,remarks",
            "P1,E1,2024-01-31,10000,8000,ACC1,Jan payroll",
            "P2,E1,2024-02-29,18000,16000,ACC1,Feb payroll jump",
            "P3,E999,2024-02-29,5000,4000,ACC9,Ghost employee",
        ]
    )

    employees = parse_payroll_employee_csv(io.BytesIO(employees_csv.encode("utf-8")))
    entries = parse_payroll_entries_csv(io.BytesIO(entries_csv.encode("utf-8")))
    save_payroll_employees(engagement_id, employees)
    save_payroll_entries(engagement_id, entries)

    findings = run_payroll_rules(engagement_id)
    codes = {f.code for f in findings}

    assert "PAYROLL_GHOST_EMPLOYEE" in codes
    assert "PAYROLL_SHARED_BANK_ACCOUNT" in codes
    assert "PAYROLL_ABNORMAL_INCREMENT" in codes

    abnormal = next(f for f in findings if f.code == "PAYROLL_ABNORMAL_INCREMENT")
    assert Decimal(abnormal.metadata["current_net_pay"]) == Decimal("16000")
