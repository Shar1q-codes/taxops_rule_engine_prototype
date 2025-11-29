import json
from pathlib import Path

from engine import RuleEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_doc(name: str) -> dict:
    with (ROOT / "sample_data" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_misc_valid_no_errors():
    engine = RuleEngine()
    doc = _load_doc("misc_valid.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    assert not [f for f in findings if f.get("severity") == "error"]


def test_misc_issues_trigger_rules():
    engine = RuleEngine()
    doc = _load_doc("misc_issues.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    codes = {f.get("id") for f in findings}

    expected = {
        "MISC_PAYER_TIN_REQUIRED",
        "MISC_RECIPIENT_TIN_FORMAT",
        "MISC_AMOUNTS_NONNEGATIVE",
        "MISC_RENTS_WITHHOLDING_SANITY",
        "MISC_WITHHOLDING_RATIO_SANITY",
        "MISC_MEDICAL_PAYMENTS_TAX_RELATIONSHIP",
        "MISC_OTHER_INCOME_PRESENTATION",
        "MISC_ATTORNEY_PAYMENTS_SANITY",
        "MISC_STATE_TAX_NONNEGATIVE",
        "MISC_STATE_TAX_VS_INCOME_SANITY",
        "MISC_STATE_CODE_FORMAT",
        "MISC_REQUIRED_PAYER_INFO",
        "MISC_REQUIRED_RECIPIENT_INFO",
    }
    assert expected.issubset(codes)
