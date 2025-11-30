import json
from pathlib import Path

from engine import RuleEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_doc(name: str) -> dict:
    with (ROOT / "sample_data" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_q1099_valid_doc_passes_all_rules():
    engine = RuleEngine()
    doc = _load_doc("q1099_valid.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    assert doc.get("doc_type") == "1099-Q"
    assert not [f for f in findings if f.get("severity") == "error"]


def test_q1099_issues_doc_triggers_expected_failures():
    engine = RuleEngine()
    doc = _load_doc("q1099_issues.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    codes = {f.get("id") for f in findings}
    expected = {
        "Q1099_PAYER_TIN_REQUIRED",
        "Q1099_RECIPIENT_TIN_REQUIRED",
        "Q1099_TAX_YEAR_REASONABLE",
        "Q1099_NONNEGATIVE_AMOUNTS",
        "Q1099_EARNINGS_PLUS_BASIS_NOT_GT_GROSS",
        "Q1099_ONE_PROGRAM_TYPE_FLAG",
        "Q1099_STATE_LIST_LENGTHS_MATCH",
        "Q1099_TRUSTEE_TRANSFER_HAS_ZERO_EARNINGS",
    }
    assert expected.issubset(codes)
