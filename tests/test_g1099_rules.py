import json
from pathlib import Path

from engine import RuleEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_doc(name: str) -> dict:
    with (ROOT / "sample_data" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_g1099_valid_doc_passes_all_rules():
    engine = RuleEngine()
    doc = _load_doc("g1099_valid.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    assert doc.get("doc_type") == "1099-G"
    assert not [f for f in findings if f.get("severity") == "error"]


def test_g1099_issues_doc_triggers_expected_failures():
    engine = RuleEngine()
    doc = _load_doc("g1099_issues.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    codes = {f.get("id") for f in findings}
    expected = {
        "G1099_PAYER_TIN_REQUIRED",
        "G1099_RECIPIENT_TIN_REQUIRED",
        "G1099_TAX_YEAR_REASONABLE",
        "G1099_NONNEGATIVE_AMOUNTS",
        "G1099_WITHHELD_NOT_EXCESSIVE",
        "G1099_STATE_LIST_LENGTHS_MATCH",
        "G1099_BOX2_TAX_YEAR_PRESENT",
    }
    assert expected.issubset(codes)
