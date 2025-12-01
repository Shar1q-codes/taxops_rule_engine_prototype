from __future__ import annotations

from datetime import date, time as dt_time
from decimal import Decimal
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class Account(BaseModel):
    """Canonical account metadata."""

    id: str
    code: str
    name: str
    type: Literal["asset", "liability", "equity", "income", "expense", "other"]


class Counterparty(BaseModel):
    """Counterparty to a transaction (customer, vendor, bank, etc.)."""

    id: str
    name: str
    category: Optional[Literal["customer", "vendor", "employee", "bank", "other"]] = None


class TransactionLine(BaseModel):
    """A single debit/credit line in a transaction."""

    account_code: str
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")


class Transaction(BaseModel):
    """Journal entry/transaction grouped by an id."""

    id: str
    date: date
    description: str
    lines: List[TransactionLine] = Field(default_factory=list)
    counterparty_id: Optional[str] = None
    source: Optional[str] = None  # e.g. "GL", "manual_journal"
    posted_by: Optional[str] = None


class TrialBalanceRow(BaseModel):
    """Trial balance row covering opening, activity, and closing balances."""

    account_code: str
    account_name: str
    opening_balance: Decimal
    debit: Decimal
    credit: Decimal
    closing_balance: Decimal


class BankEntry(BaseModel):
    """Normalized bank statement entry."""

    id: str
    date: date
    time: Optional[dt_time] = None
    description: str
    amount: Decimal  # positive for inflow, negative for outflow
    balance: Optional[Decimal] = None
    account_number: Optional[str] = None
    reference: Optional[str] = None


class PayrollEmployee(BaseModel):
    """Employee master data for payroll."""

    id: str
    name: str
    bank_account: Optional[str] = None
    department: Optional[str] = None
    active: bool = True


class PayrollEntry(BaseModel):
    """Payroll entry for a given period."""

    id: str
    employee_id: str
    period: date
    gross_pay: Decimal
    net_pay: Decimal
    bank_account: Optional[str] = None
    remarks: Optional[str] = None


class InventoryItem(BaseModel):
    """Inventory item master."""

    id: str
    name: str
    category: Optional[str] = None
    unit: Optional[str] = None
    cost_price: Optional[Decimal] = None
    selling_price: Optional[Decimal] = None


class InventoryMovement(BaseModel):
    """Inventory movement (stock ledger) entry."""

    id: str
    item_id: str
    date: date
    quantity: Decimal
    movement_type: Optional[str] = None  # e.g. purchase, sale, write_off
    reference: Optional[str] = None


__all__ = [
    "Account",
    "Counterparty",
    "TransactionLine",
    "Transaction",
    "TrialBalanceRow",
    "BankEntry",
    "PayrollEmployee",
    "PayrollEntry",
    "InventoryItem",
    "InventoryMovement",
]
