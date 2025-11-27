from pathlib import Path

import yaml

from rule_engine import apply_rules
from rule_engine.context import get_context_for_year


RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "1099_int.yaml"


def load_rules():
    with RULES_PATH.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or []


def test_1099_int_multiple_findings_on_suspicious_form():
    rules = load_rules()
    document = {
        "doc_id": "uuid-1099-1",
        "doc_type": "1099-INT",
        "tax_year": 2024,
        "payer": {"name": "Big Bank, N.A.", "tin": "12-3456789"},
        "recipient": {"name": "John Doe", "tin": "123-45-678"},
        "amounts": {
            "interest_income": 0.0,
            "federal_tax_withheld": 500.0,
            "early_withdrawal_penalty": 0.0,
            "investment_expenses": 0.0,
            "tax_exempt_interest": -10.0,
            "specified_private_activity_bond_interest": 0.0,
            "market_discount": 0.0,
            "bond_premium": 0.0,
        },
        "meta": {},
    }

    context = get_context_for_year(document["tax_year"])
    findings = apply_rules(document, rules, context)
    codes = {f["code"] for f in findings}

    assert "INT_ZERO_INTEREST_NONZERO_WITHHOLDING" in codes
    assert "INT_MISSING_RECIPIENT_TIN" in codes
    assert "INT_NEGATIVE_INTEREST_OR_TAX" in codes


def test_1099_int_clean_document_has_no_findings():
    rules = load_rules()
    document = {
        "doc_id": "uuid-1099-2",
        "doc_type": "1099-INT",
        "tax_year": 2024,
        "payer": {"name": "Big Bank, N.A.", "tin": "12-3456789"},
        "recipient": {"name": "Jane Smith", "tin": "987-65-4329"},
        "amounts": {
            "interest_income": 500.0,
            "federal_tax_withheld": 0.0,
            "early_withdrawal_penalty": 0.0,
            "investment_expenses": 0.0,
            "tax_exempt_interest": 0.0,
            "specified_private_activity_bond_interest": 0.0,
            "market_discount": 0.0,
            "bond_premium": 0.0,
        },
        "meta": {},
    }

    context = get_context_for_year(document["tax_year"])
    findings = apply_rules(document, rules, context)

    assert findings == []
