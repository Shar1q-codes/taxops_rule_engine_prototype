from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable, List, Mapping, Optional

from backend.accounting_models import GLEntry, Transaction, TransactionLine, TrialBalanceRow

TB_HEADERS = {"account_code", "account_name", "opening_balance", "debit", "credit", "closing_balance"}
GL_HEADERS = {"txn_id", "date", "description", "account_code", "debit", "credit"}


def _to_decimal(raw: str) -> Decimal:
    try:
        return Decimal(str(raw or "0"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid numeric value: {raw}") from exc


def _parse_datetime(raw: str | None) -> Optional[datetime]:
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


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


def _parse_date_value(value: date | str) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


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


def parse_gl_entries_from_csv(content: str) -> List[GLEntry]:
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames or not GL_HEADERS.issubset({h.strip() for h in reader.fieldnames if h}):
        missing = GL_HEADERS - set(reader.fieldnames or [])
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    return _parse_gl_entries(list(reader))


def parse_gl_entries_from_rows(rows: Iterable[Mapping]) -> List[GLEntry]:
    flat_rows: List[Mapping] = []
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(f"Invalid GL row at position {idx}: expected object")
        flat_rows.append(row)
    return _parse_gl_entries(flat_rows)


def _group_transactions(flat_rows: List[Mapping]) -> List[Transaction]:
    grouped: dict[str, Transaction] = {}
    for idx, row in enumerate(flat_rows, start=1):
        try:
            txn_id = str(row["txn_id"]).strip()
            txn_date = row["date"]
            txn_date_parsed = _parse_date_value(txn_date)
            user_id = (row.get("user_id") or None) if isinstance(row, Mapping) else None
            approved_by = (row.get("approved_by") or None) if isinstance(row, Mapping) else None
            posted_at = _parse_datetime(row.get("posted_at")) if isinstance(row, Mapping) else None
            approved_at = _parse_datetime(row.get("approved_at")) if isinstance(row, Mapping) else None
            source = (row.get("source") or None) if isinstance(row, Mapping) else None
            txn = grouped.get(txn_id)
            if not txn:
                txn = Transaction(
                    id=txn_id,
                    date=txn_date_parsed,
                    description=str(row["description"]).strip(),
                    lines=[],
                    user_id=user_id,
                    approved_by=approved_by,
                    posted_at=posted_at,
                    approved_at=approved_at,
                    source=source,
                )
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


def _parse_gl_entries(flat_rows: List[Mapping]) -> List[GLEntry]:
    entries: List[GLEntry] = []
    for idx, row in enumerate(flat_rows, start=1):
        try:
            txn_id = str(row["txn_id"]).strip()
            account_code = str(row["account_code"]).strip()
            txn_date_parsed = _parse_date_value(row["date"])
            description = str(row["description"]).strip()
            debit = _to_decimal(row.get("debit", "0"))
            credit = _to_decimal(row.get("credit", "0"))
            amount = debit - credit
            user_id = (row.get("user_id") or None) if isinstance(row, Mapping) else None
            approved_by = (row.get("approved_by") or None) if isinstance(row, Mapping) else None
            posted_at = _parse_datetime(row.get("posted_at")) if isinstance(row, Mapping) else None
            approved_at = _parse_datetime(row.get("approved_at")) if isinstance(row, Mapping) else None
            source = (row.get("source") or None) if isinstance(row, Mapping) else None

            entries.append(
                GLEntry(
                    id=f"{txn_id}-{idx}",
                    account=account_code,
                    date=txn_date_parsed,
                    description=description,
                    amount=amount,
                    debit=debit,
                    credit=credit,
                    user_id=user_id,
                    approved_by=approved_by,
                    posted_at=posted_at,
                    approved_at=approved_at,
                    source=source,
                )
            )
        except KeyError as exc:
            raise ValueError(f"Missing required GL column in row {idx}: {exc}") from exc
        except Exception as exc:
            raise ValueError(f"Invalid GL row at position {idx}: {exc}") from exc
    return entries
