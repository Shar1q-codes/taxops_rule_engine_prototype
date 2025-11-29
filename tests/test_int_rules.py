import json
from pathlib import Path

from engine import RuleEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_doc(name: str) -> dict:
    with (ROOT / "sample_data" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_int_valid_has_no_errors():
    engine = RuleEngine()
    doc = _load_doc("int_valid.json")

    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    assert not [f for f in findings if f.get("severity") == "error"]


def test_int_issues_triggers_expected_rules():
    engine = RuleEngine()
    doc = _load_doc("int_issues.json")

    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    codes = {f.get("id") for f in findings}

    expected = {
        "INT_TAX_YEAR_RANGE",
        "INT_PAYER_TIN_FORMAT",
        "INT_RECIPIENT_TIN_FORMAT",
        "INT_AMOUNTS_NONNEGATIVE",
        "INT_BACKUP_WITHHOLDING_RATIO",
        "INT_PRIVATE_ACTIVITY_NOT_EXCEED_TAX_EXEMPT",
    }
    assert expected.issubset(codes)
