from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from io import TextIOWrapper
from typing import BinaryIO, List

from backend.accounting_models import BooksTaxRow, TaxReturnRow

DATE_FMT = "%Y-%m-%d"


def parse_returns_csv(file_obj: BinaryIO) -> List[TaxReturnRow]:
    wrapper = TextIOWrapper(file_obj, encoding="utf-8")
    reader = csv.DictReader(wrapper)
    rows: List[TaxReturnRow] = []
    for row in reader:
        if not row:
            continue
        rows.append(
            TaxReturnRow(
                period=row["period"].strip(),
                tax_type=row.get("tax_type", "GST").strip() or "GST",
                turnover_return=Decimal(row["turnover_return"]),
                tax_paid=Decimal(row["tax_paid"]),
                filing_date=datetime.strptime(row["filing_date"].strip(), DATE_FMT).date(),
                due_date=datetime.strptime(row["due_date"].strip(), DATE_FMT).date(),
            )
        )
    return rows


def parse_books_tax_csv(file_obj: BinaryIO) -> List[BooksTaxRow]:
    wrapper = TextIOWrapper(file_obj, encoding="utf-8")
    reader = csv.DictReader(wrapper)
    rows: List[BooksTaxRow] = []
    for row in reader:
        if not row:
            continue
        rows.append(
            BooksTaxRow(
                period=row["period"].strip(),
                tax_type=row.get("tax_type", "GST").strip() or "GST",
                turnover_books=Decimal(row["turnover_books"]),
            )
        )
    return rows
