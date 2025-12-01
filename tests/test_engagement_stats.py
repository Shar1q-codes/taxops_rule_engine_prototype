from backend.db import SessionLocal, init_db
from backend.db_models import ClientORM, EngagementORM, FindingORM
from backend.engagement_stats import compute_engagement_stats


def test_engagement_stats_aggregates_by_domain_and_severity():
    init_db()
    with SessionLocal() as db:
        db.query(FindingORM).delete()
        db.query(EngagementORM).delete()
        db.query(ClientORM).delete()
        db.commit()
        client = ClientORM(name="Stats Client", code="STATS", status="active")
        db.add(client)
        db.flush()
        engagement = EngagementORM(client_id=client.id, name="E-Stats", status="open")
        db.add(engagement)
        db.flush()

        eid = engagement.id

        rows = [
            FindingORM(
                id="f-books-1",
                engagement_id=eid,
                domain="books",
                severity="high",
                code="CODE1",
                message="msg",
                metadata_json={},
            ),
            FindingORM(
                id="f-books-2",
                engagement_id=eid,
                domain="books",
                severity="high",
                code="CODE2",
                message="msg",
                metadata_json={},
            ),
            FindingORM(
                id="f-income-1",
                engagement_id=eid,
                domain="income",
                severity="medium",
                code="CODE3",
                message="msg",
                metadata_json={},
            ),
            FindingORM(
                id="f-bank-1",
                engagement_id=eid,
                domain="bank",
                severity="low",
                code="CODE4",
                message="msg",
                metadata_json={},
            ),
        ]
        db.add_all(rows)
        db.commit()

        stats = compute_engagement_stats(db, eid)

        assert stats.engagement_id == eid
        assert stats.totals["high"] == 2
        assert stats.totals["medium"] == 1
        assert stats.totals["low"] == 1
        assert stats.totals["total"] == 4

        by_domain = {d.domain: d for d in stats.domains}
        assert by_domain["books"].high == 2
        assert by_domain["books"].total == 2
        assert by_domain["income"].medium == 1
        assert by_domain["bank"].low == 1
