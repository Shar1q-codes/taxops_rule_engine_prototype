import json
from pathlib import Path

from engine import RuleEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_doc(name: str) -> dict:
    with (ROOT / "sample_data" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_w2_clean_stays_clean():
    engine = RuleEngine()
    doc = _load_doc("w2_valid.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    assert not [f for f in findings if f.get("severity") == "error"]
    assert not {f.get("id") for f in findings} & {
        "W2_EMPLOYEE_SSN_PLAUSIBILITY",
        "W2_EMPLOYER_EIN_PLAUSIBILITY",
        "W2_SS_WAGES_AT_OR_BELOW_BASE",
        "W2_WAGE_BOX_RELATIONSHIP_SANITY",
        "W2_STATE_TAX_VS_WAGES_SANITY",
        "W2_STATE_WAGES_VS_BOX1_SANITY",
    }


def test_w2_tin_and_math_issues():
    engine = RuleEngine()
    doc = _load_doc("w2_issues.json")
    # introduce high SS wages and tax mismatch
    doc["wages"]["social_security_wages"] = 300000
    doc["wages"]["social_security_tax_withheld"] = 0
    doc["employee"]["ssn"] = "111-11-1111"
    doc["employer"]["ein"] = "00-0000000"

    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    codes = {f.get("id") for f in findings}
    assert "W2_EMPLOYEE_SSN_PLAUSIBILITY" in codes
    assert "W2_EMPLOYER_EIN_PLAUSIBILITY" in codes
    assert "W2_SS_WAGES_AT_OR_BELOW_BASE" in codes
    assert "W2_SS_TAX_MATCHES_RATE" in codes


def test_w2_state_tax_sanity():
    engine = RuleEngine()
    doc = _load_doc("w2_valid.json")
    doc["state"]["state_wages"] = 1000
    doc["state"]["state_tax_withheld"] = 500
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    codes = {f.get("id") for f in findings}
    assert "W2_STATE_TAX_VS_WAGES_SANITY" in codes
