from __future__ import annotations

from backend.db import SessionLocal
from backend.db_models import ClientORM, EngagementORM


def seed_demo_data() -> None:
    """Seed a demo client/engagement if tables are empty."""
    with SessionLocal() as db:
        client = db.query(ClientORM).first()
        if not client:
            client = ClientORM(name="Demo Client", code="DEMO", status="active")
            db.add(client)
            db.flush()
        engagement = db.query(EngagementORM).filter(EngagementORM.client_id == client.id).first()
        if not engagement:
            engagement = EngagementORM(
                client_id=client.id,
                name="FY24 Audit",
                status="open",
                period_start=None,
                period_end=None,
            )
            db.add(engagement)
        db.commit()
