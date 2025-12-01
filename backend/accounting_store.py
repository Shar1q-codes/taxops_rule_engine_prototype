from __future__ import annotations

from typing import Dict, List

from backend.accounting_models import BankEntry, PayrollEmployee, PayrollEntry, TrialBalanceRow, Transaction

# Simple in-memory store keyed by engagement id. Replace with a real DB later.
_store: Dict[str, Dict[str, List]] = {
    "trial_balances": {},
    "transactions": {},
}

_BANK_ENTRIES: Dict[str, List[BankEntry]] = {}
_PAYROLL_EMPLOYEES: Dict[str, List[PayrollEmployee]] = {}
_PAYROLL_ENTRIES: Dict[str, List[PayrollEntry]] = {}


def save_trial_balance(engagement_id: str, rows: List[TrialBalanceRow]) -> None:
    _store["trial_balances"][engagement_id] = rows


def save_transactions(engagement_id: str, txns: List[Transaction]) -> None:
    _store["transactions"][engagement_id] = txns


def get_trial_balance(engagement_id: str) -> List[TrialBalanceRow]:
    return _store["trial_balances"].get(engagement_id, [])


def get_transactions(engagement_id: str) -> List[Transaction]:
    return _store["transactions"].get(engagement_id, [])


def save_bank_entries(engagement_id: str, entries: List[BankEntry]) -> None:
    _BANK_ENTRIES[engagement_id] = entries


def get_bank_entries(engagement_id: str) -> List[BankEntry]:
    return _BANK_ENTRIES.get(engagement_id, [])


def save_payroll_employees(engagement_id: str, employees: List[PayrollEmployee]) -> None:
    _PAYROLL_EMPLOYEES[engagement_id] = employees


def get_payroll_employees(engagement_id: str) -> List[PayrollEmployee]:
    return _PAYROLL_EMPLOYEES.get(engagement_id, [])


def save_payroll_entries(engagement_id: str, entries: List[PayrollEntry]) -> None:
    _PAYROLL_ENTRIES[engagement_id] = entries


def get_payroll_entries(engagement_id: str) -> List[PayrollEntry]:
    return _PAYROLL_ENTRIES.get(engagement_id, [])


def clear_engagement(engagement_id: str) -> None:
    """Test helper to drop any cached rows for an engagement."""
    _store["trial_balances"].pop(engagement_id, None)
    _store["transactions"].pop(engagement_id, None)
    _BANK_ENTRIES.pop(engagement_id, None)
    _PAYROLL_EMPLOYEES.pop(engagement_id, None)
    _PAYROLL_ENTRIES.pop(engagement_id, None)
