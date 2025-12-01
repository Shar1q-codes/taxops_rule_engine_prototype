import io
from decimal import Decimal

from backend.accounting_store import clear_engagement, save_inventory_items, save_inventory_movements
from backend.inventory_ingestion import parse_inventory_items_csv, parse_inventory_movements_csv
from backend.inventory_rules import run_inventory_rules


def test_inventory_ingestion_and_rules():
    engagement_id = "eng-inventory"
    clear_engagement(engagement_id)

    items_csv = "\n".join(
        [
            "item_id,name,category,unit,cost_price,selling_price",
            "I1,Widget A,Parts,pcs,10,8",  # margin sanity (selling below cost)
            "I2,Widget B,Parts,pcs,5,15",
            "I3,Widget C,Parts,pcs,2,5",  # no movements -> slow moving
        ]
    )

    movements_csv = "\n".join(
            [
                "movement_id,item_id,date,quantity,movement_type,reference",
                "M1,I1,2024-01-05,-50,sale,ref1",
                "M2,I1,2024-01-06,-150,write_off,ref2",  # write-off
                "M3,I2,2024-01-05,20,purchase,ref3",
                "M4,I2,2024-01-06,-30,sale,ref4",
                "M5,I2,2024-01-07,5,adjustment,ref5",
            ]
        )

    items = parse_inventory_items_csv(io.BytesIO(items_csv.encode("utf-8")))
    movements = parse_inventory_movements_csv(io.BytesIO(movements_csv.encode("utf-8")))

    save_inventory_items(engagement_id, items)
    save_inventory_movements(engagement_id, movements)

    findings = run_inventory_rules(engagement_id)
    codes = {f.code for f in findings}

    assert "INVENTORY_NEGATIVE_STOCK" in codes
    assert "INVENTORY_LARGE_WRITE_OFF" in codes
    assert "INVENTORY_SLOW_MOVING" in codes
    assert "INVENTORY_MARGIN_SANITY" in codes

    negative = next(f for f in findings if f.code == "INVENTORY_NEGATIVE_STOCK")
    assert negative.metadata["item_id"] == "I1"
