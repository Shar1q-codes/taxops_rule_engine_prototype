import os

os.environ["AUTH_BYPASS"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from backend import app as app_module  # noqa: E402
from backend.db import init_db  # noqa: E402
from backend.seed import seed_demo_data  # noqa: E402
from backend.db import SessionLocal  # noqa: E402
from backend.db_models import ClientORM  # noqa: E402


client = TestClient(app_module.app)


def setup_module():
    os.environ["AUTH_BYPASS"] = "true"
    init_db()
    seed_demo_data()


def test_auth_me_returns_user():
    resp = client.get("/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("user", {}).get("id") == "demo-user"


def test_clients_listing():
    resp = client.get("/api/clients")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data and data[0]["id"]


def test_client_engagements():
    with SessionLocal() as db:
        client_row = db.query(ClientORM).first()
        assert client_row
        resp = client.get(f"/api/clients/{client_row.id}/engagements")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data and data[0]["clientId"] == client_row.id
