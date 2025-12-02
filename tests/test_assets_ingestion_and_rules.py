from io import BytesIO
from textwrap import dedent

from backend.assets_ingestion import parse_assets_csv, parse_depreciation_csv
from backend.assets_rules import run_assets_rules
from backend.accounting_store import save_assets, save_depreciation_entries
from backend.db import init_db


def make_bytes(s: str) -> BytesIO:
    return BytesIO(dedent(s).lstrip().encode("utf-8"))


def test_assets_ingestion_and_rules_basic():
    init_db()
    engagement_id = "eng-assets-1"

    assets_csv = make_bytes(
        """asset_code,description,category,acquisition_date,acquisition_cost,useful_life_years,disposal_date
        A1,Machine 1,Plant,2020-01-01,100000,50,
        A2,Machine 2,Plant,2021-01-01,50000,10,2023-12-31
        A3,Machine 3,Plant,2022-01-01,30000,8,
        """
    )
    deps_csv = make_bytes(
        """asset_code,period_end,depreciation_expense,accumulated_depreciation,net_book_value
        A1,2024-12-31,10000,40000,60000
        A2,2024-12-31,10000,30000,20000
        """
    )

    assets = parse_assets_csv(assets_csv)
    deps = parse_depreciation_csv(deps_csv)

    save_assets(engagement_id, assets)
    save_depreciation_entries(engagement_id, deps)

    findings = run_assets_rules(engagement_id)
    codes = {f.code for f in findings}

    assert "ASSET_USEFUL_LIFE_EXCEEDS_POLICY" in codes
    assert "ASSET_NO_DEPRECIATION_RECORDED" in codes
    assert "ASSET_DISPOSAL_WITH_NONZERO_NBV" in codes
