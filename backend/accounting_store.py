from __future__ import annotations

from typing import Dict, List

from backend.accounting_models import TrialBalanceRow, Transaction

# Simple in-memory store keyed by engagement id. Replace with a real DB later.
_store: Dict[str, Dict[str, List]] = {
    "trial_balances": {},
    "transactions": {},
}


def save_trial_balance(engagement_id: str, rows: List[TrialBalanceRow]) -> None:
    _store["trial_balances"][engagement_id] = rows


def save_transactions(engagement_id: str, txns: List[Transaction]) -> None:
    _store["transactions"][engagement_id] = txns


def get_trial_balance(engagement_id: str) -> List[TrialBalanceRow]:
    return _store["trial_balances"].get(engagement_id, [])


def get_transactions(engagement_id: str) -> List[Transaction]:
    return _store["transactions"].get(engagement_id, [])


def clear_engagement(engagement_id: str) -> None:
    """Test helper to drop any cached rows for an engagement."""
    _store["trial_balances"].pop(engagement_id, None)
    _store["transactions"].pop(engagement_id, None)
