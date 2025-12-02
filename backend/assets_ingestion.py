from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from io import TextIOWrapper
from typing import BinaryIO, List

from backend.accounting_models import DepreciationEntry, FixedAsset

DATE_FMT = "%Y-%m-%d"


def parse_assets_csv(file_obj: BinaryIO) -> List[FixedAsset]:
    wrapper = TextIOWrapper(file_obj, encoding="utf-8")
    reader = csv.DictReader(wrapper)
    assets: List[FixedAsset] = []
    for idx, row in enumerate(reader):
        if not row:
            continue
        disposal_raw = (row.get("disposal_date") or "").strip()
        disposal_date = datetime.strptime(disposal_raw, DATE_FMT).date() if disposal_raw else None
        assets.append(
            FixedAsset(
                id=row.get("id") or f"asset-{idx}",
                asset_code=row["asset_code"].strip(),
                description=row.get("description", "").strip(),
                category=row.get("category", "").strip(),
                acquisition_date=datetime.strptime(row["acquisition_date"].strip(), DATE_FMT).date(),
                acquisition_cost=Decimal(row["acquisition_cost"]),
                useful_life_years=Decimal(row["useful_life_years"]),
                disposal_date=disposal_date,
            )
        )
    return assets


def parse_depreciation_csv(file_obj: BinaryIO) -> List[DepreciationEntry]:
    wrapper = TextIOWrapper(file_obj, encoding="utf-8")
    reader = csv.DictReader(wrapper)
    entries: List[DepreciationEntry] = []
    for idx, row in enumerate(reader):
        if not row:
            continue
        entries.append(
            DepreciationEntry(
                id=row.get("id") or f"dep-{idx}",
                asset_code=row["asset_code"].strip(),
                period_end=datetime.strptime(row["period_end"].strip(), DATE_FMT).date(),
                depreciation_expense=Decimal(row["depreciation_expense"]),
                accumulated_depreciation=Decimal(row["accumulated_depreciation"]),
                net_book_value=Decimal(row["net_book_value"]),
            )
        )
    return entries
