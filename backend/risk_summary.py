from __future__ import annotations

from typing import Dict, List

from sqlalchemy.orm import Session

from backend.db_models import ClientORM, EngagementORM, FindingORM
from backend.schemas import DomainRiskSummary, EngagementRiskSummary

SEVERITY_WEIGHTS: Dict[str, int] = {
    "LOW": 1,
    "MEDIUM": 3,
    "HIGH": 6,
    "CRITICAL": 10,
}

MAX_RISK_BASELINE = 100


def compute_engagement_risk_summary(db: Session, engagement: EngagementORM) -> EngagementRiskSummary:
    findings = db.query(FindingORM).filter(FindingORM.engagement_id == engagement.id).all()

    if not findings:
        return EngagementRiskSummary(
            engagement_id=engagement.id,
            overall_score=0,
            total_findings=0,
            by_severity={k: 0 for k in SEVERITY_WEIGHTS.keys()},
            domains=[],
        )

    findings_by_domain: Dict[str, List[FindingORM]] = {}
    global_by_severity: Dict[str, int] = {k: 0 for k in SEVERITY_WEIGHTS.keys()}

    for f in findings:
        domain = str(f.domain)
        severity = str(f.severity or "").upper()
        findings_by_domain.setdefault(domain, []).append(f)
        if severity in global_by_severity:
            global_by_severity[severity] += 1

    domain_summaries: List[DomainRiskSummary] = []
    overall_raw = 0

    for domain, domain_findings in findings_by_domain.items():
        domain_by_severity: Dict[str, int] = {k: 0 for k in SEVERITY_WEIGHTS.keys()}
        domain_raw_score = 0

        for f in domain_findings:
            severity = str(f.severity or "").upper()
            if severity in domain_by_severity:
                domain_by_severity[severity] += 1
            domain_raw_score += SEVERITY_WEIGHTS.get(severity, 0)

        overall_raw += domain_raw_score
        domain_summaries.append(
            DomainRiskSummary(
                domain=domain,
                score=domain_raw_score,  # raw weighted sum for now
                total_findings=len(domain_findings),
                by_severity=domain_by_severity,
            )
        )

    if overall_raw <= 0:
        overall_score = 0
    else:
        overall_score = min(100, int(overall_raw * 100 / MAX_RISK_BASELINE))

    return EngagementRiskSummary(
        engagement_id=engagement.id,
        overall_score=overall_score,
        total_findings=len(findings),
        by_severity=global_by_severity,
        domains=domain_summaries,
    )
