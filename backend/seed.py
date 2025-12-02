from __future__ import annotations

from backend.db import SessionLocal
from backend.db_models import ClientORM, EngagementORM, FirmMembershipORM, FirmORM, UserORM
from backend.security import hash_password


def seed_demo_data() -> None:
    """Seed a demo client/engagement if tables are empty."""
    with SessionLocal() as db:
        firm = db.query(FirmORM).filter(FirmORM.slug == "demo-firm").first()
        if not firm:
            firm = FirmORM(id="demo-firm", name="Demo CPA Firm", slug="demo-firm")
            db.add(firm)
            db.flush()

        user = db.query(UserORM).filter(UserORM.email == "demo@taxops.local").first()
        if not user:
            user = UserORM(
                id="demo-user",
                email="demo@taxops.local",
                hashed_password=hash_password("password"),
                full_name="Demo User",
                is_active=1,
                is_superuser=1,
            )
            db.add(user)
            db.flush()

        membership = (
            db.query(FirmMembershipORM)
            .filter(FirmMembershipORM.user_id == user.id, FirmMembershipORM.firm_id == firm.id)
            .first()
        )
        if not membership:
            membership = FirmMembershipORM(user_id=user.id, firm_id=firm.id, role="owner")
            db.add(membership)

        client = db.query(ClientORM).first()
        if not client:
            client = ClientORM(name="Demo Client", code="DEMO", status="active", firm_id=firm.id)
            db.add(client)
            db.flush()
        elif not client.firm_id:
            client.firm_id = firm.id
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
