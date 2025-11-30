import json
from pathlib import Path

from engine import RuleEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_doc(name: str) -> dict:
    with (ROOT / "sample_data" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_w9_valid_no_errors():
    engine = RuleEngine()
    doc = _load_doc("w9_valid.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    assert not [f for f in findings if f.get("severity") == "error"]


def test_w9_issues_trigger_rules():
    engine = RuleEngine()
    doc = _load_doc("w9_issues.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))
    codes = {f.get("id") for f in findings}

    expected = {
        "W9_TAXPAYER_NAME_REQUIRED",
        "W9_TIN_PRESENT_FOR_CLASS",
        "W9_SSN_FORMAT_VALID",
        "W9_LLC_CLASS_REQUIRED_WHEN_LLC",
        "W9_ADDRESS_REQUIRED",
        "W9_STATE_CODE_FORMAT",
        "W9_ZIP_CODE_FORMAT",
        "W9_EXEMPT_PAYEE_CODE_FORMAT",
        "W9_CERTIFICATION_SIGNED",
        "W9_ZERO_PLACEHOLDER_SANITY",
    }
    assert expected.issubset(codes)
