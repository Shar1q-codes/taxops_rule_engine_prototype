from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from sqlalchemy.orm import Session

from backend.db_models import FindingORM
from backend.schemas import DomainStats, EngagementStatsResponse

SEVERITIES = ("high", "medium", "low")


def compute_engagement_stats(db: Session, engagement_id: str) -> EngagementStatsResponse:
    rows: List[FindingORM] = db.query(FindingORM).filter(FindingORM.engagement_id == engagement_id).all()

    per_domain: Dict[str, Dict[str, int]] = defaultdict(lambda: {s: 0 for s in SEVERITIES})
    totals = {s: 0 for s in SEVERITIES}
    totals["total"] = 0

    for r in rows:
        sev = (r.severity or "").lower()
        if sev not in SEVERITIES:
            continue
        per_domain[r.domain][sev] += 1
        totals[sev] += 1
        totals["total"] += 1

    domain_stats: List[DomainStats] = []
    for domain, sev_counts in per_domain.items():
        total = sum(sev_counts[s] for s in SEVERITIES)
        domain_stats.append(
            DomainStats(
                domain=domain,
                high=sev_counts["high"],
                medium=sev_counts["medium"],
                low=sev_counts["low"],
                total=total,
            )
        )

    domain_stats.sort(key=lambda d: d.total, reverse=True)

    return EngagementStatsResponse(
        engagement_id=engagement_id,
        domains=domain_stats,
        totals=totals,
    )
