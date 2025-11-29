import json
from pathlib import Path

from engine import RuleEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_doc(name: str) -> dict:
    with (ROOT / "sample_data" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_nec_valid_no_errors():
    engine = RuleEngine()
    doc = _load_doc("nec_valid.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    assert not [f for f in findings if f.get("severity") == "error"]


def test_nec_issues_trigger_rules():
    engine = RuleEngine()
    doc = _load_doc("nec_issues.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    codes = {f.get("id") for f in findings}

    expected = {
        "NEC_PAYER_TIN_REQUIRED",
        "NEC_RECIPIENT_TIN_FORMAT",
        "NEC_AMOUNTS_NONNEGATIVE",
        "NEC_WITHHOLDING_RATIO_SANITY",
        "NEC_STATE_TAX_NONNEGATIVE",
        "NEC_STATE_TAX_VS_COMPENSATION",
        "NEC_STATE_CODE_FORMAT",
        "NEC_REQUIRED_PAYER_INFO",
        "NEC_REQUIRED_RECIPIENT_INFO",
    }
    assert expected.issubset(codes)

    doc_zero_comp = {**doc, "amounts": {**doc["amounts"], "box_1_nonemployee_compensation": 0}}
    findings_zero = engine.evaluate(doc_zero_comp, form_type=doc_zero_comp.get("doc_type"), tax_year=doc_zero_comp.get("tax_year"))
    codes_zero = {f.get("id") for f in findings_zero}
    assert "NEC_COMP_REQUIRED_FOR_WITHHOLDING" in codes_zero
