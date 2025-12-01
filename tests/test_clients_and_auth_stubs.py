import os

os.environ["AUTH_BYPASS"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from backend import app as app_module  # noqa: E402


client = TestClient(app_module.app)


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
    assert data and data[0]["id"] == "client-1"


def test_client_engagements():
    resp = client.get("/api/clients/client-1/engagements")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["clientId"] == "client-1"
