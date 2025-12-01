from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List

from pydantic import BaseModel

from backend.accounting_models import TrialBalanceRow


class GLRow(BaseModel):
    txn_id: str
    date: date
    description: str
    account_code: str
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")


class TrialBalanceIngestResponse(BaseModel):
    rows_ingested: int
    total_debit: Decimal
    total_credit: Decimal


class GLIngestResponse(BaseModel):
    transactions_ingested: int
    total_debit: Decimal
    total_credit: Decimal


class TrialBalancePayload(BaseModel):
    rows: List[TrialBalanceRow]
