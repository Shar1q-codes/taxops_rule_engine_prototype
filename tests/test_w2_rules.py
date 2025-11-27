from pathlib import Path

import yaml

from rule_engine import apply_rules


RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "w2.yaml"


def load_rules():
    with RULES_PATH.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or []


def test_w2_rules_trigger_multiple_findings():
    rules = load_rules()
    context = {
        "limits": {"social_security_wage_base": 168_600},
        "rates": {"social_security_rate": 0.062, "medicare_rate": 0.0145},
    }
    document = {
        "doc_id": "uuid-123",
        "doc_type": "W2",
        "tax_year": 2024,
        "taxpayer": {"name": "John Doe", "ssn": "123-45-678"},
        "employer": {"name": "ACME Inc.", "ein": "12-3456789", "state": "CA"},
        "amounts": {
            "wages": 80000,
            "federal_withholding": 0,
            "state_withholding": 2000,
            "social_security_wages": 80000,
            "social_security_tax": 0,
            "medicare_wages": 80000,
            "medicare_tax": 0,
        },
        "flags": {"ocr_quality": 0.9},
        "meta": {},
    }

    findings = apply_rules(document, rules, context=context)
    codes = {f["code"] for f in findings}

    assert "W2_ZERO_FED_WITHHOLDING" in codes
    assert "W2_SOCSEC_TAX_RATE_MISMATCH" in codes
    assert "W2_MEDICARE_TAX_RATE_MISMATCH" in codes
    assert "W2_MISSING_TAXPAYER_SSN" in codes


def test_w2_rules_clean_document_has_no_findings():
    rules = load_rules()
    context = {
        "limits": {"social_security_wage_base": 168_600},
        "rates": {"social_security_rate": 0.062, "medicare_rate": 0.0145},
    }
    document = {
        "doc_id": "uuid-456",
        "doc_type": "W2",
        "tax_year": 2024,
        "taxpayer": {"name": "Jane Smith", "ssn": "987-65-4329"},
        "employer": {"name": "Widget Corp", "ein": "98-7654321", "state": "NY"},
        "amounts": {
            "wages": 85_000,
            "federal_withholding": 12_000,
            "state_withholding": 3_000,
            "social_security_wages": 85_000,
            "social_security_tax": 0.062 * 85_000,
            "medicare_wages": 85_000,
            "medicare_tax": 0.0145 * 85_000,
        },
        "flags": {"ocr_quality": 0.95},
        "meta": {},
    }

    findings = apply_rules(document, rules, context=context)

    assert findings == []


def test_w2_ss_wages_mismatch():
    rules = load_rules()
    context = {
        "limits": {"social_security_wage_base": 168_600},
        "rates": {"social_security_rate": 0.062, "medicare_rate": 0.0145},
    }
    document = {
        "doc_id": "uuid-789",
        "doc_type": "W2",
        "tax_year": 2024,
        "taxpayer": {"name": "John Doe", "ssn": "123-45-6789"},
        "employer": {"name": "ACME Inc.", "ein": "12-3456789", "state": "CA"},
        "amounts": {
            "wages": 85_000,
            "federal_withholding": 12_000,
            "state_withholding": 3_000,
            "social_security_wages": 80_000,
            "social_security_tax": 0.062 * 80_000,
            "medicare_wages": 85_000,
            "medicare_tax": 0.0145 * 85_000,
        },
        "flags": {},
        "meta": {},
    }
    findings = apply_rules(document, rules, context=context)
    codes = {f["code"] for f in findings}
    assert "W2_SS_WAGES_MISMATCH" in codes

    document_close = {
        **document,
        "amounts": {**document["amounts"], "social_security_wages": 84_500},
    }
    findings_close = apply_rules(document_close, rules, context=context)
    codes_close = {f["code"] for f in findings_close}
    assert "W2_SS_WAGES_MISMATCH" not in codes_close


def test_w2_ein_malformed_or_missing():
    rules = load_rules()
    context = {
        "limits": {"social_security_wage_base": 168_600},
        "rates": {"social_security_rate": 0.062, "medicare_rate": 0.0145},
    }
    base_doc = {
        "doc_id": "uuid-ein",
        "doc_type": "W2",
        "tax_year": 2024,
        "taxpayer": {"name": "Jane Smith", "ssn": "987-65-4321"},
        "employer": {"name": "Widget Co", "ein": "", "state": "NY"},
        "amounts": {"wages": 50_000, "federal_withholding": 5_000, "social_security_wages": 50_000, "social_security_tax": 0.062 * 50_000, "medicare_wages": 50_000, "medicare_tax": 0.0145 * 50_000},
        "flags": {},
        "meta": {},
    }
    findings_missing = apply_rules(base_doc, rules, context=context)
    codes_missing = {f["code"] for f in findings_missing}
    assert "W2_EIN_MALFORMED_OR_MISSING" in codes_missing

    valid_doc = {**base_doc, "employer": {**base_doc["employer"], "ein": "12-3456789"}}
    findings_valid = apply_rules(valid_doc, rules, context=context)
    codes_valid = {f["code"] for f in findings_valid}
    assert "W2_EIN_MALFORMED_OR_MISSING" not in codes_valid


def test_w2_fica_over_cap():
    rules = load_rules()
    context = {
        "limits": {"social_security_wage_base": 168_600},
        "rates": {"social_security_rate": 0.062, "medicare_rate": 0.0145},
    }
    over_cap_doc = {
        "doc_id": "uuid-fica",
        "doc_type": "W2",
        "tax_year": 2024,
        "taxpayer": {"name": "High Earner", "ssn": "123-45-6789"},
        "employer": {"name": "BigCo", "ein": "98-7654321", "state": "CA"},
        "amounts": {
            "wages": 210_000,
            "federal_withholding": 40_000,
            "social_security_wages": 200_000,
            "social_security_tax": 0.062 * 200_000,
            "medicare_wages": 210_000,
            "medicare_tax": 0.0145 * 210_000,
        },
        "flags": {},
        "meta": {},
    }
    findings_over = apply_rules(over_cap_doc, rules, context=context)
    codes_over = {f["code"] for f in findings_over}
    assert "W2_FICA_OVER_CAP" in codes_over

    under_cap_doc = {**over_cap_doc, "amounts": {**over_cap_doc["amounts"], "social_security_wages": 150_000}}
    findings_under = apply_rules(under_cap_doc, rules, context=context)
    codes_under = {f["code"] for f in findings_under}
    assert "W2_FICA_OVER_CAP" not in codes_under
