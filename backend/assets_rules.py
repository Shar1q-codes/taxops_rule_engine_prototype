from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Dict, List

from backend.accounting_store import get_assets, get_depreciation_entries
from backend.domain_rules import DomainFinding, make_finding_id

MAX_USEFUL_LIFE_YEARS = Decimal("40")


def run_assets_rules(engagement_id: str) -> List[DomainFinding]:
    assets = get_assets(engagement_id)
    deps = get_depreciation_entries(engagement_id)

    findings: List[DomainFinding] = []
    idx = 0

    dep_by_asset: Dict[str, List] = defaultdict(list)
    for d in deps:
        dep_by_asset[d.asset_code].append(d)
    for code in dep_by_asset:
        dep_by_asset[code].sort(key=lambda d: d.period_end)

    for asset in assets:
        if asset.useful_life_years > MAX_USEFUL_LIFE_YEARS:
            findings.append(
                DomainFinding(
                    id=make_finding_id("assets", "ASSET_USEFUL_LIFE_EXCEEDS_POLICY", idx),
                    engagement_id=engagement_id,
                    domain="assets",
                    severity="medium",
                    code="ASSET_USEFUL_LIFE_EXCEEDS_POLICY",
                    message="Asset useful life exceeds standard policy threshold.",
                    metadata={
                        "asset_code": asset.asset_code,
                        "category": asset.category,
                        "useful_life_years": str(asset.useful_life_years),
                    },
                )
            )
            idx += 1

    for asset in assets:
        if asset.asset_code not in dep_by_asset:
            findings.append(
                DomainFinding(
                    id=make_finding_id("assets", "ASSET_NO_DEPRECIATION_RECORDED", idx),
                    engagement_id=engagement_id,
                    domain="assets",
                    severity="high",
                    code="ASSET_NO_DEPRECIATION_RECORDED",
                    message="Asset exists in FAR but has no depreciation entries.",
                    metadata={
                        "asset_code": asset.asset_code,
                        "category": asset.category,
                        "acquisition_date": str(asset.acquisition_date),
                        "acquisition_cost": str(asset.acquisition_cost),
                    },
                )
            )
            idx += 1

    for asset in assets:
        if not asset.disposal_date:
            continue
        entries = dep_by_asset.get(asset.asset_code, [])
        if not entries:
            continue
        last_entry = entries[-1]
        if last_entry.net_book_value > Decimal("1"):
            findings.append(
                DomainFinding(
                    id=make_finding_id("assets", "ASSET_DISPOSAL_WITH_NONZERO_NBV", idx),
                    engagement_id=engagement_id,
                    domain="assets",
                    severity="high",
                    code="ASSET_DISPOSAL_WITH_NONZERO_NBV",
                    message="Disposed asset still shows material net book value.",
                    metadata={
                        "asset_code": asset.asset_code,
                        "disposal_date": str(asset.disposal_date),
                        "last_period_end": str(last_entry.period_end),
                        "net_book_value": str(last_entry.net_book_value),
                    },
                )
            )
            idx += 1

    return findings
