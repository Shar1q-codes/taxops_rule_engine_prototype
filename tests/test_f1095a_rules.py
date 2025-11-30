import json
from pathlib import Path

from engine import RuleEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_doc(name: str) -> dict:
    with (ROOT / "sample_data" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_f1095a_valid_no_errors():
    engine = RuleEngine()
    doc = _load_doc("f1095a_valid.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    assert not [f for f in findings if f.get("severity") == "error"]


def test_f1095a_issues_trigger_rules():
    engine = RuleEngine()
    doc = _load_doc("f1095a_issues.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    codes = {f.get("id") for f in findings}

    expected = {
        "A1095_RECIPIENT_TIN_REQUIRED",
        "A1095_RECIPIENT_TIN_FORMAT",
        "A1095_REQUIRED_RECIPIENT_INFO",
        "A1095_REQUIRED_ISSUER_INFO",
        "A1095_AMOUNTS_NONNEGATIVE",
        "A1095_PREMIUM_WITHOUT_COVERAGE_PERSON",
        "A1095_MONTH_ROW_INCOMPLETE",
        "A1095_TOTAL_APTC_REASONABLE",
        "A1095_APTC_WITHOUT_PREMIUM",
        "A1095_APTC_WITHOUT_SLCSP",
        "A1095_SLCSP_WITHOUT_PREMIUM",
    }
    assert expected.issubset(codes)
