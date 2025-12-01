from backend.db import SessionLocal, init_db
from backend.db_models import ClientORM, EngagementORM, FindingORM
from backend.domain_rules import DomainFinding
from backend.findings_persistence import save_domain_findings


def test_findings_persist_and_override():
    init_db()
    with SessionLocal() as db:
        db.query(FindingORM).delete()
        db.query(EngagementORM).delete()
        db.query(ClientORM).delete()
        db.commit()
        client = ClientORM(name="FClient", code="FC", status="active")
        db.add(client)
        db.flush()
        engagement = EngagementORM(client_id=client.id, name="E1", status="open")
        db.add(engagement)
        db.commit()

        engagement_id = engagement.id

        f1 = DomainFinding(
            id="f1",
            engagement_id=engagement_id,
            domain="income",
            severity="medium",
            code="TEST",
            message="test finding",
            metadata={"foo": "bar"},
        )
        save_domain_findings(db, engagement_id, "income", [f1])

        rows = db.query(FindingORM).filter(FindingORM.engagement_id == engagement_id).all()
        assert len(rows) == 1
        assert rows[0].id == "f1"

        f2 = DomainFinding(
            id="f2",
            engagement_id=engagement_id,
            domain="income",
            severity="high",
            code="TEST2",
            message="second finding",
            metadata={},
        )
        save_domain_findings(db, engagement_id, "income", [f2])
        rows = db.query(FindingORM).filter(FindingORM.engagement_id == engagement_id).all()
        assert len(rows) == 1
        assert rows[0].id == "f2"
