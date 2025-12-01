from backend.db import SessionLocal, init_db
from backend.db_models import ClientORM


def test_db_scaffolding_creates_tables():
    init_db()
    with SessionLocal() as db:
        client = ClientORM(name="Demo Client", code="DEMO")
        db.add(client)
        db.commit()
        db.refresh(client)
        assert client.id
