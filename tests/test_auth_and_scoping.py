import os

import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from backend.db import SessionLocal, init_db
from backend.db_models import ClientORM, EngagementORM, FirmORM, FirmMembershipORM, UserORM

os.environ["AUTH_BYPASS"] = "false"

client = TestClient(app_module.app)


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _get_firm_by_name(name: str):
    with SessionLocal() as db:
        return db.query(FirmORM).filter(FirmORM.name == name).first()


@pytest.fixture(autouse=True)
def setup_db():
    os.environ["AUTH_BYPASS"] = "false"
    init_db()
    yield
    # clean up cross-test data that might accumulate for these tables
    with SessionLocal() as db:
        db.query(EngagementORM).delete()
        db.query(ClientORM).delete()
        db.query(FirmMembershipORM).delete()
        db.query(UserORM).delete()
        db.query(FirmORM).delete()
        db.commit()


def test_register_and_login_flow():
    register_body = {"firm": {"name": "Firm A"}, "user": {"email": "owner@example.com", "password": "secret", "full_name": "Owner"}}
    resp = client.post("/auth/register-firm", json=register_body)
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    me_resp = client.get("/auth/me", headers=_auth_header(token))
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["user"]["email"] == "owner@example.com"
    assert me_data["firm"]["name"] == "Firm A"

    bad_login = client.post("/auth/login", json={"email": "owner@example.com", "password": "wrong"})
    assert bad_login.status_code == 401


def test_firm_scoping_blocks_other_firm_access():
    # Create Firm 1 + user
    resp1 = client.post(
        "/auth/register-firm",
        json={"firm": {"name": "Firm One"}, "user": {"email": "firm1@example.com", "password": "secret", "full_name": "F1"}},
    )
    assert resp1.status_code == 200
    token1 = resp1.json()["access_token"]

    # Create Firm 2 + user
    resp2 = client.post(
        "/auth/register-firm",
        json={"firm": {"name": "Firm Two"}, "user": {"email": "firm2@example.com", "password": "secret", "full_name": "F2"}},
    )
    assert resp2.status_code == 200
    token2 = resp2.json()["access_token"]

    firm1 = _get_firm_by_name("Firm One")
    firm2 = _get_firm_by_name("Firm Two")

    # Create clients for each firm
    with SessionLocal() as db:
        client1 = ClientORM(name="Client F1", code="CF1", status="active", firm_id=firm1.id)
        db.add(client1)
        db.flush()
        engagement1 = EngagementORM(client_id=client1.id, name="F1 Engagement", status="open")
        db.add(engagement1)

        client2 = ClientORM(name="Client F2", code="CF2", status="active", firm_id=firm2.id)
        db.add(client2)
        db.flush()
        engagement2 = EngagementORM(client_id=client2.id, name="F2 Engagement", status="open")
        db.add(engagement2)
        db.commit()

        client1_id = client1.id
        eng1_id = engagement1.id
        client2_id = client2.id
        eng2_id = engagement2.id

    # Firm 1 user should see only Firm1 client
    list_resp = client.get("/api/clients", headers=_auth_header(token1))
    assert list_resp.status_code == 200
    clients = list_resp.json()
    ids = {c["id"] for c in clients}
    assert client1_id in ids
    assert client2_id not in ids

    # Firm 2 user cannot access Firm1 engagements
    resp_eng = client.get(f"/api/clients/{client1_id}/engagements", headers=_auth_header(token2))
    assert resp_eng.status_code == 404

    # Firm 2 user stats for Firm1 engagement should be blocked
    resp_stats = client.get(f"/api/engagements/{eng1_id}/stats", headers=_auth_header(token2))
    assert resp_stats.status_code == 404

    # Firm 1 user should not access Firm2 engagement
    resp_stats_f1 = client.get(f"/api/engagements/{eng2_id}/stats", headers=_auth_header(token1))
    assert resp_stats_f1.status_code == 404
