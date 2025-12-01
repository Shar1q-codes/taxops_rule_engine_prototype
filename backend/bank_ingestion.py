from __future__ import annotations

import csv
import io
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import BinaryIO, List

from backend.accounting_models import BankEntry


def _parse_date(raw: str) -> date:
    raw = raw.strip()
    # Try ISO first.
    try:
        return date.fromisoformat(raw)
    except ValueError:
        pass
    # Fallback for DD/MM/YYYY
    try:
        return datetime.strptime(raw, "%d/%m/%Y").date()
    except ValueError as exc:
        raise ValueError(f"Invalid date format: {raw}") from exc


def _parse_time(raw: str | None) -> time | None:
    if not raw:
        return None
    try:
        return time.fromisoformat(raw.strip())
    except ValueError:
        # Ignore unparsable times for now.
        return None


def _to_decimal(raw: str | None) -> Decimal:
    try:
        cleaned = (raw or "").replace(",", "").strip() or "0"
        return Decimal(cleaned)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid decimal value: {raw}") from exc


def parse_bank_csv(file_obj: BinaryIO) -> List[BankEntry]:
    content = file_obj.read()
    if isinstance(content, bytes):
        text = content.decode("utf-8")
    else:
        text = str(content)
    reader = csv.DictReader(io.StringIO(text))
    entries: List[BankEntry] = []
    for idx, row in enumerate(reader, start=1):
        if not row:
            continue
        try:
            entries.append(
                BankEntry(
                    id=f"bank-{idx}",
                    date=_parse_date(str(row.get("date", "")).strip()),
                    time=_parse_time(row.get("time")),
                    description=str(row.get("description", "")).strip(),
                    amount=_to_decimal(row.get("amount")),
                    balance=_to_decimal(row["balance"]) if row.get("balance") not in (None, "") else None,
                    account_number=str(row.get("account_number") or "").strip() or None,
                    reference=str(row.get("reference") or "").strip() or None,
                )
            )
        except Exception as exc:
            raise ValueError(f"Invalid bank row {idx}: {exc}") from exc
    return entries
