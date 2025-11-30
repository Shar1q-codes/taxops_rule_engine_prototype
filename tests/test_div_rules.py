import json
from pathlib import Path

from engine import RuleEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_doc(name: str) -> dict:
    with (ROOT / "sample_data" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_div_valid_no_errors():
    engine = RuleEngine()
    doc = _load_doc("div_valid.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    assert not [f for f in findings if f.get("severity") == "error"]


def test_div_issues_trigger_rules():
    engine = RuleEngine()
    doc = _load_doc("div_issues.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    codes = {f.get("id") for f in findings}

    expected = {
        "DIV_PAYER_TIN_REQUIRED",
        "DIV_PAYER_TIN_FORMAT",
        "DIV_RECIPIENT_TIN_FORMAT",
        "DIV_AMOUNTS_NONNEGATIVE",
        "DIV_QUALIFIED_NOT_EXCEED_ORDINARY",
        "DIV_CAP_GAIN_WITH_ZERO_ORDINARY",
        "DIV_WITHHOLDING_RATIO_SANITY",
        "DIV_FOREIGN_TAX_WITHOUT_COUNTRY",
        "DIV_199A_NOT_EXCEED_ORDINARY",
        "DIV_PRIVATE_ACTIVITY_NOT_EXCEED_EXEMPT_INT",
        "DIV_STATE_TAX_NONNEGATIVE",
        "DIV_STATE_CODE_FORMAT",
        "DIV_REQUIRED_PAYER_INFO",
        "DIV_REQUIRED_RECIPIENT_INFO",
    }
    assert expected.issubset(codes)
