import json
from pathlib import Path

from engine import RuleEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_doc(name: str) -> dict:
    with (ROOT / "sample_data" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_f1098_valid_no_errors():
    engine = RuleEngine()
    doc = _load_doc("f1098_valid.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    assert not [f for f in findings if f.get("severity") == "error"]


def test_f1098_issues_trigger_rules():
    engine = RuleEngine()
    doc = _load_doc("f1098_issues.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    codes = {f.get("id") for f in findings}

    expected = {
        "F1098_LENDER_TIN_REQUIRED",
        "F1098_LENDER_TIN_FORMAT",
        "F1098_BORROWER_TIN_FORMAT",
        "F1098_AMOUNTS_NONNEGATIVE",
        "F1098_PRINCIPAL_WITHOUT_INTEREST",
        "F1098_REFUNDED_INTEREST_NOT_EXCEED_INTEREST",
        "F1098_POINTS_WITHOUT_INTEREST",
        "F1098_ORIGINATION_DATE_PRESENT",
        "F1098_PROPERTY_ADDRESS_PRESENT",
        "F1098_ACCOUNT_OR_PROPERTY_IDENTIFIER_PRESENT",
        "F1098_REQUIRED_LENDER_INFO",
        "F1098_REQUIRED_BORROWER_INFO",
    }
    assert expected.issubset(codes)
