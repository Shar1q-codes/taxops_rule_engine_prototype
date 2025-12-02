import os

from fastapi.testclient import TestClient

from backend import app as app_module
from backend.db import SessionLocal, init_db
from backend.db_models import ClientORM, EngagementORM, FindingORM, FirmMembershipORM, FirmORM, UserORM
from backend.risk_summary import compute_engagement_risk_summary, SEVERITY_WEIGHTS
from backend.security import hash_password


def _make_firm(db, name: str):
    firm = FirmORM(name=name)
    db.add(firm)
    db.flush()
    return firm


def _make_user(db, email: str):
    user = UserORM(email=email, hashed_password=hash_password("secret"), is_active=1, is_superuser=0)
    db.add(user)
    db.flush()
    return user


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_compute_engagement_risk_summary_basic():
    init_db()
    with SessionLocal() as db:
        db.query(FindingORM).delete()
        db.query(EngagementORM).delete()
        db.query(ClientORM).delete()
        db.commit()

        firm = _make_firm(db, "Risk Firm")
        client = ClientORM(name="Risk Client", code="RISK", status="active", firm_id=firm.id)
        db.add(client)
        db.flush()
        engagement = EngagementORM(client_id=client.id, name="Risk Eng", status="open")
        db.add(engagement)
        db.flush()

        findings = [
            FindingORM(
                id="f1",
                engagement_id=engagement.id,
                domain="books",
                severity="HIGH",
                code="CODE1",
                message="m1",
                metadata_json={},
            ),
            FindingORM(
                id="f2",
                engagement_id=engagement.id,
                domain="books",
                severity="LOW",
                code="CODE2",
                message="m2",
                metadata_json={},
            ),
            FindingORM(
                id="f3",
                engagement_id=engagement.id,
                domain="assets",
                severity="CRITICAL",
                code="CODE3",
                message="m3",
                metadata_json={},
            ),
        ]
        db.add_all(findings)
        db.commit()

        summary = compute_engagement_risk_summary(db, engagement)

        assert summary.engagement_id == engagement.id
        assert summary.total_findings == 3
        assert summary.by_severity["HIGH"] == 1
        assert summary.by_severity["LOW"] == 1
        assert summary.by_severity["CRITICAL"] == 1
        books_score = SEVERITY_WEIGHTS["HIGH"] + SEVERITY_WEIGHTS["LOW"]
        assets_score = SEVERITY_WEIGHTS["CRITICAL"]
        domain_scores = {d.domain: d.score for d in summary.domains}
        assert domain_scores["books"] == books_score
        assert domain_scores["assets"] == assets_score
        assert summary.overall_score > 0


def test_compute_engagement_risk_summary_empty():
    init_db()
    with SessionLocal() as db:
        db.query(FindingORM).delete()
        db.query(EngagementORM).delete()
        db.query(ClientORM).delete()
        db.commit()

        firm = _make_firm(db, "Empty Firm")
        client = ClientORM(name="Empty Client", code="EMPTY", status="active", firm_id=firm.id)
        db.add(client)
        db.flush()
        engagement = EngagementORM(client_id=client.id, name="No Findings", status="open")
        db.add(engagement)
        db.commit()

        summary = compute_engagement_risk_summary(db, engagement)
        assert summary.overall_score == 0
        assert summary.total_findings == 0
        assert all(v == 0 for v in summary.by_severity.values())
        assert summary.domains == []


def test_risk_summary_endpoint_enforces_firm_scoping():
    os.environ["AUTH_BYPASS"] = "false"
    init_db()
    client = TestClient(app_module.app)
    # Firm A
    resp_a = client.post(
        "/auth/register-firm",
        json={"firm": {"name": "Firm A"}, "user": {"email": "a@example.com", "password": "secret", "full_name": "A"}},
    )
    assert resp_a.status_code == 200
    token_a = resp_a.json()["access_token"]
    with SessionLocal() as db:
        firm_a = db.query(FirmORM).filter(FirmORM.name == "Firm A").first()
        client_a = ClientORM(name="Client A", code="CA", status="active", firm_id=firm_a.id)
        db.add(client_a)
        db.flush()
        engagement_a = EngagementORM(client_id=client_a.id, name="Eng A", status="open")
        db.add(engagement_a)
        db.flush()
        db.add(
            FindingORM(
                id="fa1",
                engagement_id=engagement_a.id,
                domain="books",
                severity="HIGH",
                code="CODEA",
                message="msg",
                metadata_json={},
            )
        )
        db.commit()
        eng_a_id = engagement_a.id

    # Firm B
    resp_b = client.post(
        "/auth/register-firm",
        json={"firm": {"name": "Firm B"}, "user": {"email": "b@example.com", "password": "secret", "full_name": "B"}},
    )
    assert resp_b.status_code == 200
    token_b = resp_b.json()["access_token"]
    with SessionLocal() as db:
        firm_b = db.query(FirmORM).filter(FirmORM.name == "Firm B").first()
        client_b = ClientORM(name="Client B", code="CB", status="active", firm_id=firm_b.id)
        db.add(client_b)
        db.flush()
        engagement_b = EngagementORM(client_id=client_b.id, name="Eng B", status="open")
        db.add(engagement_b)
        db.commit()
        eng_b_id = engagement_b.id

    # Access own engagement
    ok_resp = client.get(f"/api/engagements/{eng_a_id}/risk-summary", headers=_auth_header(token_a))
    assert ok_resp.status_code == 200
    body = ok_resp.json()
    assert body["engagement_id"] == eng_a_id

    # Access other firm's engagement should be 404
    denied = client.get(f"/api/engagements/{eng_b_id}/risk-summary", headers=_auth_header(token_a))
    assert denied.status_code == 404
