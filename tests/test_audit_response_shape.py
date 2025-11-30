import os
from pathlib import Path

from fastapi.testclient import TestClient

from engine import rule_engine

# Ensure local auth bypass is enabled before importing the app
os.environ["AUTH_BYPASS"] = "true"

from backend import app as app_module  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
client = TestClient(app_module.app)


def test_audit_endpoint_returns_structured_response():
    payload_path = ROOT / "sample_data" / "w2_issues.json"
    resp = client.post(
        "/audit-document",
        files={"file": ("w2_issues.json", payload_path.read_bytes(), "application/json")},
    )
    assert resp.status_code == 200
    body = resp.json()

    for key in [
        "request_id",
        "doc_id",
        "doc_type",
        "tax_year",
        "received_at",
        "processed_at",
        "status",
        "summary",
        "document_metadata",
        "findings",
        "engine",
    ]:
        assert key in body

    assert body["status"] == "ok"
    assert isinstance(body["findings"], list)
    assert body["summary"]["total_findings"] == len(body["findings"])
    assert body["summary"]["total_rules_evaluated"] == len(rule_engine.registry.get_rules("W2"))
    for sev_key in ("error", "warning", "info"):
        assert sev_key in body["summary"]["by_severity"]

    finding_codes = {f["id"] for f in body["findings"]}
    assert "W2_SSN_FORMAT" in finding_codes

    sample_finding = body["findings"][0]
    for field in [
        "id",
        "code",
        "severity",
        "rule_type",
        "category",
        "message",
        "doc_type",
        "tax_year",
        "fields",
        "field_paths",
        "citations",
        "rule_source",
        "condition",
        "extras",
    ]:
        assert field in sample_finding
