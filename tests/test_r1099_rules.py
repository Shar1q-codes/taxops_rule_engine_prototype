import json
from pathlib import Path

from engine import RuleEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_doc(name: str) -> dict:
    with (ROOT / "sample_data" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_r1099_valid_doc_passes_all_rules():
    engine = RuleEngine()
    doc = _load_doc("r1099_valid.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    assert doc.get("doc_type") == "1099-R"
    assert not [f for f in findings if f.get("severity") == "error"]


def test_r1099_issues_doc_triggers_expected_failures():
    engine = RuleEngine()
    doc = _load_doc("r1099_issues.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    codes = {f.get("id") for f in findings}
    expected = {
        "R1099_PAYER_TIN_REQUIRED",
        "R1099_RECIPIENT_TIN_REQUIRED",
        "R1099_NONNEGATIVE_AMOUNTS",
        "R1099_TAXABLE_AMOUNT_NOT_GT_GROSS",
        "R1099_TAX_YEAR_REASONABLE",
        "R1099_DISTRIBUTION_CODE_REQUIRED",
    }
    assert expected.issubset(codes)
