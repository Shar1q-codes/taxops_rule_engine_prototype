import os
from pathlib import Path

from fastapi.testclient import TestClient

# Bypass auth for tests before importing the app
os.environ["AUTH_BYPASS"] = "true"

from backend import app as app_module  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
client = TestClient(app_module.app)


def test_audit_report_returns_html():
    payload_path = ROOT / "sample_data" / "w2_issues.json"
    resp = client.post(
        "/audit-report",
        files={"file": ("w2_issues.json", payload_path.read_bytes(), "application/json")},
    )
    assert resp.status_code == 200
    content_type = resp.headers.get("content-type", "")
    assert "text/html" in content_type
    body = resp.text
    assert "W2" in body
    assert "2024" in body
    assert "W2_SSN_FORMAT" in body or "W2_SSN" in body
