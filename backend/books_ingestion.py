from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Iterable, List, Mapping

from backend.accounting_models import Transaction, TransactionLine, TrialBalanceRow

TB_HEADERS = {"account_code", "account_name", "opening_balance", "debit", "credit", "closing_balance"}
GL_HEADERS = {"txn_id", "date", "description", "account_code", "debit", "credit"}


def _to_decimal(raw: str) -> Decimal:
    try:
        return Decimal(str(raw or "0"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid numeric value: {raw}") from exc


def parse_tb_rows_from_csv(content: str) -> List[TrialBalanceRow]:
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames or not TB_HEADERS.issubset({h.strip() for h in reader.fieldnames if h}):
        missing = TB_HEADERS - set(reader.fieldnames or [])
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    rows: List[TrialBalanceRow] = []
    for idx, row in enumerate(reader, start=1):
        if not row:
            continue
        try:
            rows.append(
                TrialBalanceRow(
                    account_code=str(row["account_code"]).strip(),
                    account_name=str(row["account_name"]).strip(),
                    opening_balance=_to_decimal(row["opening_balance"]),
                    debit=_to_decimal(row["debit"]),
                    credit=_to_decimal(row["credit"]),
                    closing_balance=_to_decimal(row["closing_balance"]),
                )
            )
        except KeyError as exc:
            raise ValueError(f"Missing required column in row {idx}: {exc}") from exc
    return rows


def parse_tb_rows_from_list(rows: Iterable[Mapping]) -> List[TrialBalanceRow]:
    parsed: List[TrialBalanceRow] = []
    for idx, item in enumerate(rows, start=1):
        try:
            parsed.append(TrialBalanceRow.parse_obj(item))
        except Exception as exc:
            raise ValueError(f"Invalid trial balance row at position {idx}: {exc}") from exc
    return parsed


def parse_transactions_from_csv(content: str) -> List[Transaction]:
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames or not GL_HEADERS.issubset({h.strip() for h in reader.fieldnames if h}):
        missing = GL_HEADERS - set(reader.fieldnames or [])
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    flat_rows = list(reader)
    return _group_transactions(flat_rows)


def parse_transactions_from_rows(rows: Iterable[Mapping]) -> List[Transaction]:
    flat_rows: List[Mapping] = []
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(f"Invalid GL row at position {idx}: expected object")
        flat_rows.append(row)
    return _group_transactions(flat_rows)


def _group_transactions(flat_rows: List[Mapping]) -> List[Transaction]:
    grouped: dict[str, Transaction] = {}
    for idx, row in enumerate(flat_rows, start=1):
        try:
            txn_id = str(row["txn_id"]).strip()
            txn_date = row["date"]
            txn_date_parsed = txn_date if isinstance(txn_date, date) else date.fromisoformat(str(txn_date))
            txn = grouped.get(txn_id)
            if not txn:
                txn = Transaction(id=txn_id, date=txn_date_parsed, description=str(row["description"]).strip(), lines=[])
                grouped[txn_id] = txn
            txn.lines.append(
                TransactionLine(
                    account_code=str(row["account_code"]).strip(),
                    debit=_to_decimal(row.get("debit", "0")),
                    credit=_to_decimal(row.get("credit", "0")),
                )
            )
        except KeyError as exc:
            raise ValueError(f"Missing required GL column in row {idx}: {exc}") from exc
        except Exception as exc:
            raise ValueError(f"Invalid GL row at position {idx}: {exc}") from exc
    return list(grouped.values())
