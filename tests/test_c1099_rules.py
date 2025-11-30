import json
from pathlib import Path

from engine import RuleEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_doc(name: str) -> dict:
    with (ROOT / "sample_data" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_c1099_valid_doc_passes_all_rules():
    engine = RuleEngine()
    doc = _load_doc("c1099_valid.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    assert doc.get("doc_type") == "1099-C"
    assert not [f for f in findings if f.get("severity") == "error"]


def test_c1099_issues_doc_triggers_expected_failures():
    engine = RuleEngine()
    doc = _load_doc("c1099_issues.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    codes = {f.get("id") for f in findings}
    expected = {
        "C1099_CREDITOR_TIN_REQUIRED",
        "C1099_DEBTOR_TIN_REQUIRED",
        "C1099_TAX_YEAR_REASONABLE",
        "C1099_NONNEGATIVE_AMOUNTS",
        "C1099_EVENT_DATE_REQUIRED_WITH_DISCHARGE",
        "C1099_EVENT_CODE_REQUIRED_WITH_DISCHARGE",
        "C1099_INTEREST_NOT_GT_DISCHARGED",
        "C1099_FMV_NOT_GT_DISCHARGED_X_FACTOR",
        "C1099_STATE_LIST_LENGTHS_MATCH",
    }
    assert expected.issubset(codes)
