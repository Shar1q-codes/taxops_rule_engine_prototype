import os

os.environ["AUTH_BYPASS"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from backend import app as app_module  # noqa: E402


client = TestClient(app_module.app)


def test_firm_info_success():
    resp = client.get("/api/firm/info", headers={"Authorization": "Bearer test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data and "name" in data


def test_firm_summary_success():
    resp = client.get("/api/firm/summary", headers={"Authorization": "Bearer test"})
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"totalClients", "activeEngagements", "highSeverityFindings", "upcomingReports"}
