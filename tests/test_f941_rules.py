import json
from pathlib import Path

from engine import RuleEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_doc(name: str) -> dict:
    with (ROOT / "sample_data" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_f941_valid_no_errors():
    engine = RuleEngine()
    doc = _load_doc("f941_valid.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    assert not [f for f in findings if f.get("severity") == "error"]


def test_f941_issues_trigger_rules():
    engine = RuleEngine()
    doc = _load_doc("f941_issues.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    codes = {f.get("id") for f in findings}

    expected = {
        "F941_EMPLOYER_EIN_REQUIRED",
        "F941_EMPLOYER_EIN_FORMAT",
        "F941_REQUIRED_EMPLOYER_INFO",
        "F941_TAX_YEAR_AND_QUARTER_REQUIRED",
        "F941_AMOUNTS_NONNEGATIVE",
        "F941_SS_TAX_RATE_CONSISTENCY",
        "F941_SS_TIPS_TAX_RATE_CONSISTENCY",
        "F941_MEDICARE_TAX_RATE_CONSISTENCY",
        "F941_ADDL_MEDICARE_TAX_CONSISTENCY",
        "F941_TOTAL_TAXES_AFTER_ADJUSTMENTS_CONSISTENCY",
        "F941_TOTAL_TAXES_AFTER_CREDITS_CONSISTENCY",
        "F941_BALANCE_DUE_VS_OVERPAYMENT_EXCLUSIVITY",
        "F941_BALANCE_DUE_COMPUTATION",
        "F941_OVERPAYMENT_COMPUTATION",
        "F941_EMPLOYEE_COUNT_VS_WAGES_SANITY",
        "F941_WAGES_VS_FICA_BASE_SANITY",
    }
    assert expected.issubset(codes)
