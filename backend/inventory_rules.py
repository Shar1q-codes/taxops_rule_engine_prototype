from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Dict, List

from backend.accounting_store import get_inventory_items, get_inventory_movements
from backend.domain_rules import DomainFinding, make_finding_id


def run_inventory_rules(engagement_id: str) -> List[DomainFinding]:
    items = get_inventory_items(engagement_id)
    moves = get_inventory_movements(engagement_id)
    findings: List[DomainFinding] = []
    idx = 0

    if not items or not moves:
        # Still evaluate slow-moving on empty moves
        if items and not moves:
            for item in items:
                findings.append(
                    DomainFinding(
                        id=make_finding_id("inventory", "INVENTORY_SLOW_MOVING", idx),
                        engagement_id=engagement_id,
                        domain="inventory",
                        severity="low",
                        code="INVENTORY_SLOW_MOVING",
                        message="Item appears in master but has no movements (potentially slow-moving or obsolete).",
                        metadata={"item_id": item.id, "item_name": item.name},
                    )
                )
                idx += 1
        return findings

    item_map: Dict[str, Dict[str, Decimal | str | None]] = {}
    for itm in items:
        item_map[itm.id] = {
            "name": itm.name,
            "cost_price": itm.cost_price,
            "selling_price": itm.selling_price,
        }

    qty_by_item: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    write_offs_by_item: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    for mv in moves:
        qty_by_item[mv.item_id] += mv.quantity
        if mv.movement_type and mv.movement_type.lower() == "write_off":
            write_offs_by_item[mv.item_id] += abs(mv.quantity)

    for item_id, qty in qty_by_item.items():
        if qty < 0:
            findings.append(
                DomainFinding(
                    id=make_finding_id("inventory", "INVENTORY_NEGATIVE_STOCK", idx),
                    engagement_id=engagement_id,
                    domain="inventory",
                    severity="high",
                    code="INVENTORY_NEGATIVE_STOCK",
                    message="Item has negative stock based on movements.",
                    metadata={"item_id": item_id, "quantity": str(qty)},
                )
            )
            idx += 1

    for item_id, qty in write_offs_by_item.items():
        if qty >= Decimal("100"):
            findings.append(
                DomainFinding(
                    id=make_finding_id("inventory", "INVENTORY_LARGE_WRITE_OFF", idx),
                    engagement_id=engagement_id,
                    domain="inventory",
                    severity="medium",
                    code="INVENTORY_LARGE_WRITE_OFF",
                    message="Large inventory write-off detected for this item.",
                    metadata={"item_id": item_id, "write_off_quantity": str(qty)},
                )
            )
            idx += 1

    moved_items = set(qty_by_item.keys())
    for item in items:
        if item.id not in moved_items:
            findings.append(
                DomainFinding(
                    id=make_finding_id("inventory", "INVENTORY_SLOW_MOVING", idx),
                    engagement_id=engagement_id,
                    domain="inventory",
                    severity="low",
                    code="INVENTORY_SLOW_MOVING",
                    message="Item appears in master but has no movements (potentially slow-moving or obsolete).",
                    metadata={"item_id": item.id, "item_name": item.name},
                )
            )
            idx += 1

    for item in items:
        if item.cost_price is None or item.selling_price is None:
            continue
        if item.selling_price <= item.cost_price:
            findings.append(
                DomainFinding(
                    id=make_finding_id("inventory", "INVENTORY_MARGIN_SANITY", idx),
                    engagement_id=engagement_id,
                    domain="inventory",
                    severity="medium",
                    code="INVENTORY_MARGIN_SANITY",
                    message="Selling price is not sufficiently above cost price for this item.",
                    metadata={
                        "item_id": item.id,
                        "item_name": item.name,
                        "cost_price": str(item.cost_price),
                        "selling_price": str(item.selling_price),
                    },
                )
            )
            idx += 1

    return findings
