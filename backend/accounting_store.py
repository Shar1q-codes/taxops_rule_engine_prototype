from __future__ import annotations

from typing import Dict, List

from backend.accounting_models import (
    BankEntry,
    APEntry,
    DepreciationEntry,
    FixedAsset,
    BooksTaxRow,
    TaxReturnRow,
    InventoryItem,
    InventoryMovement,
    LoanAccount,
    LoanPeriodEntry,
    PayrollEmployee,
    PayrollEntry,
    TrialBalanceRow,
    Transaction,
    GLEntry,
)

# Simple in-memory store keyed by engagement id. Replace with a real DB later.
_store: Dict[str, Dict[str, List]] = {
    "trial_balances": {},
    "transactions": {},
}

_BANK_ENTRIES: Dict[str, List[BankEntry]] = {}
_PAYROLL_EMPLOYEES: Dict[str, List[PayrollEmployee]] = {}
_PAYROLL_ENTRIES: Dict[str, List[PayrollEntry]] = {}
_INVENTORY_ITEMS: Dict[str, List[InventoryItem]] = {}
_INVENTORY_MOVEMENTS: Dict[str, List[InventoryMovement]] = {}
_LOANS: Dict[str, List[LoanAccount]] = {}
_LOAN_PERIODS: Dict[str, List[LoanPeriodEntry]] = {}
_AP_ENTRIES: Dict[str, List[APEntry]] = {}
_ASSETS: Dict[str, List[FixedAsset]] = {}
_ASSET_DEPRECIATION: Dict[str, List[DepreciationEntry]] = {}
_COMPLIANCE_RETURNS: Dict[str, List[TaxReturnRow]] = {}
_COMPLIANCE_BOOKS: Dict[str, List[BooksTaxRow]] = {}
_GL_ENTRIES: Dict[str, List[GLEntry]] = {}


def save_trial_balance(engagement_id: str, rows: List[TrialBalanceRow]) -> None:
    _store["trial_balances"][engagement_id] = rows


def save_transactions(engagement_id: str, txns: List[Transaction]) -> None:
    _store["transactions"][engagement_id] = txns


def get_trial_balance(engagement_id: str) -> List[TrialBalanceRow]:
    return _store["trial_balances"].get(engagement_id, [])


def get_transactions(engagement_id: str) -> List[Transaction]:
    return _store["transactions"].get(engagement_id, [])


def save_gl_entries(engagement_id: str, entries: List[GLEntry]) -> None:
    _GL_ENTRIES[engagement_id] = entries


def get_gl_entries(engagement_id: str) -> List[GLEntry]:
    return _GL_ENTRIES.get(engagement_id, [])


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


def save_inventory_items(engagement_id: str, items: List[InventoryItem]) -> None:
    _INVENTORY_ITEMS[engagement_id] = items


def get_inventory_items(engagement_id: str) -> List[InventoryItem]:
    return _INVENTORY_ITEMS.get(engagement_id, [])


def save_inventory_movements(engagement_id: str, movements: List[InventoryMovement]) -> None:
    _INVENTORY_MOVEMENTS[engagement_id] = movements


def get_inventory_movements(engagement_id: str) -> List[InventoryMovement]:
    return _INVENTORY_MOVEMENTS.get(engagement_id, [])


def save_loans(engagement_id: str, loans: List[LoanAccount]) -> None:
    _LOANS[engagement_id] = loans


def get_loans(engagement_id: str) -> List[LoanAccount]:
    return _LOANS.get(engagement_id, [])


def save_loan_periods(engagement_id: str, periods: List[LoanPeriodEntry]) -> None:
    _LOAN_PERIODS[engagement_id] = periods


def get_loan_periods(engagement_id: str) -> List[LoanPeriodEntry]:
    return _LOAN_PERIODS.get(engagement_id, [])


def save_ap_entries(engagement_id: str, entries: List[APEntry]) -> None:
    _AP_ENTRIES[engagement_id] = entries


def get_ap_entries(engagement_id: str) -> List[APEntry]:
    return _AP_ENTRIES.get(engagement_id, [])


def save_assets(engagement_id: str, assets: List[FixedAsset]) -> None:
    _ASSETS[engagement_id] = assets


def get_assets(engagement_id: str) -> List[FixedAsset]:
    return _ASSETS.get(engagement_id, [])


def save_depreciation_entries(engagement_id: str, entries: List[DepreciationEntry]) -> None:
    _ASSET_DEPRECIATION[engagement_id] = entries


def get_depreciation_entries(engagement_id: str) -> List[DepreciationEntry]:
    return _ASSET_DEPRECIATION.get(engagement_id, [])


def save_tax_returns(engagement_id: str, rows: List[TaxReturnRow]) -> None:
    _COMPLIANCE_RETURNS[engagement_id] = rows


def get_tax_returns(engagement_id: str) -> List[TaxReturnRow]:
    return _COMPLIANCE_RETURNS.get(engagement_id, [])


def save_books_tax(engagement_id: str, rows: List[BooksTaxRow]) -> None:
    _COMPLIANCE_BOOKS[engagement_id] = rows


def get_books_tax(engagement_id: str) -> List[BooksTaxRow]:
    return _COMPLIANCE_BOOKS.get(engagement_id, [])


def clear_engagement(engagement_id: str) -> None:
    """Test helper to drop any cached rows for an engagement."""
    _store["trial_balances"].pop(engagement_id, None)
    _store["transactions"].pop(engagement_id, None)
    _BANK_ENTRIES.pop(engagement_id, None)
    _PAYROLL_EMPLOYEES.pop(engagement_id, None)
    _PAYROLL_ENTRIES.pop(engagement_id, None)
    _INVENTORY_ITEMS.pop(engagement_id, None)
    _INVENTORY_MOVEMENTS.pop(engagement_id, None)
    _LOANS.pop(engagement_id, None)
    _LOAN_PERIODS.pop(engagement_id, None)
    _AP_ENTRIES.pop(engagement_id, None)
    _ASSETS.pop(engagement_id, None)
    _ASSET_DEPRECIATION.pop(engagement_id, None)
    _COMPLIANCE_RETURNS.pop(engagement_id, None)
    _COMPLIANCE_BOOKS.pop(engagement_id, None)
    _GL_ENTRIES.pop(engagement_id, None)
