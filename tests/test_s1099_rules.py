import json
from pathlib import Path

from engine import RuleEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_doc(name: str) -> dict:
    with (ROOT / "sample_data" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_s1099_valid_doc_passes_all_rules():
    engine = RuleEngine()
    doc = _load_doc("s1099_valid.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    assert doc.get("doc_type") == "1099-S"
    assert not [f for f in findings if f.get("severity") == "error"]


def test_s1099_issues_doc_triggers_expected_failures():
    engine = RuleEngine()
    doc = _load_doc("s1099_issues.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    codes = {f.get("id") for f in findings}
    expected = {
        "S1099_FILERS_TIN_REQUIRED",
        "S1099_TRANSFEROR_TIN_REQUIRED",
        "S1099_TAX_YEAR_REASONABLE",
        "S1099_NONNEGATIVE_AMOUNTS",
        "S1099_WITHHELD_NOT_EXCESSIVE",
        "S1099_STATE_LIST_LENGTHS_MATCH",
        "S1099_CLOSING_DATE_PRESENT_WITH_GROSS",
    }
    assert expected.issubset(codes)
