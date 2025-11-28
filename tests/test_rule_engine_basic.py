from engine import RuleEngine


def test_rule_registry_loads_defaults():
    engine = RuleEngine()
    assert len(engine.registry.get_rules("W2")) >= 10
    assert 2024 in engine.registry.supported_years


def test_w2_rule_engine_flags_issues():
    engine = RuleEngine()
    doc = {
        "doc_id": "w2-bad",
        "doc_type": "W2",
        "tax_year": 2024,
        "taxpayer": {"name": "Test Taxpayer", "ssn": "123"},
        "employer": {"name": "ACME", "ein": "12-3456789", "state": "CA"},
        "amounts": {
            "wages": 85000,
            "federal_withholding": 0,
            "state_withholding": 0,
            "social_security_wages": 85000,
            "social_security_tax": 0,
            "medicare_wages": 85000,
            "medicare_tax": 0,
        },
        "flags": {"ocr_quality": 0.5},
    }

    issues = engine.evaluate(doc)
    codes = {i["id"] for i in issues}
    assert "W2_SSN_FORMAT" in codes
    assert "W2_ZERO_FED_WITHHOLDING" in codes
    assert len(issues) >= 2
