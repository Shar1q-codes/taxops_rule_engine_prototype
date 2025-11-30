import json
from pathlib import Path

from engine import RuleEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_doc(name: str) -> dict:
    with (ROOT / "sample_data" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_ssa1099_valid_no_errors():
    engine = RuleEngine()
    doc = _load_doc("ssa1099_valid.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    assert not [f for f in findings if f.get("severity") == "error"]


def test_ssa1099_issues_trigger_rules():
    engine = RuleEngine()
    doc = _load_doc("ssa1099_issues.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    codes = {f.get("id") for f in findings}

    expected = {
        "SSA1099_BENEFICIARY_TIN_REQUIRED",
        "SSA1099_BENEFICIARY_TIN_FORMAT",
        "SSA1099_BENEFICIARY_INFO_REQUIRED",
        "SSA1099_PAYER_INFO_PLAUSIBILITY",
        "SSA1099_AMOUNTS_NONNEGATIVE",
        "SSA1099_NET_BENEFITS_CONSISTENCY",
        "SSA1099_REPAID_NOT_EXCEED_PAID",
        "SSA1099_WITHHOLDING_REQUIRES_BENEFITS",
        "SSA1099_STATE_TAX_NONNEGATIVE",
        "SSA1099_STATE_TAX_VS_BENEFITS_SANITY",
        "SSA1099_STATE_CODE_FORMAT",
        "SSA1099_PLACEHOLDER_IDENTITY_SANITY",
    }
    assert expected.issubset(codes)
