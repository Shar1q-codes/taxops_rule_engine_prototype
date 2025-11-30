import json
from pathlib import Path

from engine import RuleEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_doc(name: str) -> dict:
    with (ROOT / "sample_data" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_r_valid_no_errors():
    engine = RuleEngine()
    doc = _load_doc("r_valid.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    assert not [f for f in findings if f.get("severity") == "error"]


def test_r_issues_trigger_rules():
    engine = RuleEngine()
    doc = _load_doc("r_issues.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    codes = {f.get("id") for f in findings}

    expected = {
        "R_PAYER_TIN_REQUIRED",
        "R_PAYER_TIN_FORMAT",
        "R_RECIPIENT_TIN_REQUIRED",
        "R_RECIPIENT_TIN_FORMAT",
        "R_AMOUNTS_NONNEGATIVE",
        "R_TAXABLE_NOT_EXCEED_GROSS",
        "R_CAPITAL_GAIN_NOT_EXCEED_GROSS",
        "R_EMPLOYEE_CONTRIB_NOT_EXCEED_GROSS",
        "R_WITHHOLDING_REQUIRES_GROSS",
        "R_WITHHOLDING_RATIO_SANITY",
        "R_STATE_TAX_NONNEGATIVE",
        "R_STATE_TAX_VS_GROSS_SANITY",
        "R_STATE_CODE_FORMAT",
        "R_DISTRIBUTION_CODE_VALID",
        "R_CODE_G_ROLLOVER_TAXABLE_ZERO",
        "R_CODE_G_ROLLOVER_WITHHOLDING_SANITY",
        "R_CODE_Q_ROTH_TAXABLE_SANITY",
        "R_IRA_INDICATOR_CONSISTENCY",
        "R_REQUIRED_PAYER_INFO",
        "R_REQUIRED_RECIPIENT_INFO",
    }
    assert expected.issubset(codes)
