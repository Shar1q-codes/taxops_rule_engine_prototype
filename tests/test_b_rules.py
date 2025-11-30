import json
from pathlib import Path

from engine import RuleEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_doc(name: str) -> dict:
    with (ROOT / "sample_data" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_b_valid_no_errors():
    engine = RuleEngine()
    doc = _load_doc("b_valid.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    assert not [f for f in findings if f.get("severity") == "error"]


def test_b_issues_trigger_rules():
    engine = RuleEngine()
    doc = _load_doc("b_issues.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    codes = {f.get("id") for f in findings}

    expected = {
        "B1099_BROKER_TIN_REQUIRED",
        "B1099_BROKER_TIN_FORMAT",
        "B1099_REQUIRED_BROKER_INFO",
        "B1099_RECIPIENT_TIN_FORMAT",
        "B1099_REQUIRED_RECIPIENT_INFO",
        "B1099_COST_VS_PROCEEDS_SANITY",
        "B1099_MARKET_DISCOUNT_AND_BASIS",
        "B1099_WITHHOLDING_REQUIRES_PROCEEDS",
        "B1099_WITHHOLDING_RATIO_SANITY",
        "B1099_BASIS_REPORTED_FLAG_CONSISTENCY",
        "B1099_DATES_PRESENT_FOR_TRANSACTIONS",
        "B1099_DATES_ORDER_SANITY",
    }
    assert expected.issubset(codes)
