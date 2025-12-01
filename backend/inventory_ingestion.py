from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from io import TextIOWrapper
from typing import BinaryIO, List

from backend.accounting_models import InventoryItem, InventoryMovement


def parse_inventory_items_csv(file_obj: BinaryIO) -> List[InventoryItem]:
    wrapper = TextIOWrapper(file_obj, encoding="utf-8")
    reader = csv.DictReader(wrapper)
    items: List[InventoryItem] = []
    for row in reader:
        if not row:
            continue
        cost = (row.get("cost_price") or "").strip()
        sell = (row.get("selling_price") or "").strip()
        items.append(
            InventoryItem(
                id=row["item_id"].strip(),
                name=row["name"].strip(),
                category=(row.get("category") or "").strip() or None,
                unit=(row.get("unit") or "").strip() or None,
                cost_price=Decimal(cost) if cost else None,
                selling_price=Decimal(sell) if sell else None,
            )
        )
    return items


def parse_inventory_movements_csv(file_obj: BinaryIO) -> List[InventoryMovement]:
    wrapper = TextIOWrapper(file_obj, encoding="utf-8")
    reader = csv.DictReader(wrapper)
    moves: List[InventoryMovement] = []
    for idx, row in enumerate(reader):
        if not row:
            continue
        dt = datetime.strptime(row["date"].strip(), "%Y-%m-%d").date()
        moves.append(
            InventoryMovement(
                id=row.get("movement_id") or f"move-{idx}",
                item_id=row["item_id"].strip(),
                date=dt,
                quantity=Decimal(row["quantity"]),
                movement_type=(row.get("movement_type") or "").strip() or None,
                reference=(row.get("reference") or "").strip() or None,
            )
        )
    return moves
