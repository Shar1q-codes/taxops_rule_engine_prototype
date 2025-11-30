import json
from pathlib import Path

from engine import RuleEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_doc(name: str) -> dict:
    with (ROOT / "sample_data" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_k_valid_no_errors():
    engine = RuleEngine()
    doc = _load_doc("k_valid.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    assert not [f for f in findings if f.get("severity") == "error"]


def test_k_issues_trigger_rules():
    engine = RuleEngine()
    doc = _load_doc("k_issues.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    codes = {f.get("id") for f in findings}

    expected = {
        "K_PAYER_TIN_REQUIRED",
        "K_PAYEE_TIN_REQUIRED",
        "K_PAYEE_TIN_FORMAT",
        "K_AMOUNTS_NONNEGATIVE",
        "K_MONTHLY_TOTAL_VS_GROSS_SANITY",
        "K_TRANSACTIONS_COUNT_NONNEGATIVE",
        "K_WITHHOLDING_RATIO_SANITY",
        "K_STATE_TAX_NONNEGATIVE",
        "K_STATE_TAX_VS_GROSS_SANITY",
        "K_STATE_CODE_FORMAT",
        "K_REQUIRED_PAYER_INFO",
        "K_REQUIRED_PAYEE_INFO",
        "K_MCC_PRESENCE",
    }
    assert expected.issubset(codes)
