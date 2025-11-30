import json
from pathlib import Path

from engine import RuleEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_doc(name: str) -> dict:
    with (ROOT / "sample_data" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_f5498_valid_doc_passes_all_rules():
    engine = RuleEngine()
    doc = _load_doc("f5498_valid.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    assert doc.get("doc_type") == "5498"
    assert not [f for f in findings if f.get("severity") == "error"]


def test_f5498_issues_doc_triggers_expected_failures():
    engine = RuleEngine()
    doc = _load_doc("f5498_issues.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    codes = {f.get("id") for f in findings}
    expected = {
        "F5498_TRUSTEE_TIN_REQUIRED",
        "F5498_PARTICIPANT_TIN_REQUIRED",
        "F5498_TAX_YEAR_REASONABLE",
        "F5498_NONNEGATIVE_AMOUNTS",
        "F5498_ONE_ACCOUNT_TYPE_FLAG",
        "F5498_RMD_DATE_REQUIRED_WHEN_INDICATOR_TRUE",
        "F5498_CONTRIBUTIONS_NOT_ABSURD_VS_FMV",
        "F5498_RMD_AMOUNT_NONNEGATIVE_WHEN_INDICATOR_TRUE",
    }
    assert expected.issubset(codes)
