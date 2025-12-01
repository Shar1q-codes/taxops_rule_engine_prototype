from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from backend.db_models import FindingORM
from backend.domain_rules import DomainFinding


def save_domain_findings(db: Session, engagement_id: str, domain: str, findings: Iterable[DomainFinding]) -> None:
    """Replace findings for an engagement+domain with the provided list."""
    db.query(FindingORM).filter(FindingORM.engagement_id == engagement_id, FindingORM.domain == domain).delete()
    for f in findings:
        db.add(
            FindingORM(
                id=f.id,
                engagement_id=f.engagement_id,
                domain=f.domain,
                severity=f.severity,
                code=f.code,
                message=f.message,
                metadata_json=f.metadata,
            )
        )
    db.commit()
