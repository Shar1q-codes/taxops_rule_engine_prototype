"""Synthetic scenario generators for W-2 and 1099-INT with rule-engine findings."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml

from rule_engine.core import apply_rules
from rule_engine.context import get_context_for_year


def base_w2_document(tax_year: int = 2024) -> Dict[str, Any]:
    """Return a clean W-2 document that should not trigger rules."""
    wages = 85_000
    ss_rate = 0.062
    medicare_rate = 0.0145
    return {
        "doc_id": f"w2-clean-{tax_year}",
        "doc_type": "W2",
        "tax_year": tax_year,
        "taxpayer": {"name": "Jane Smith", "ssn": "123-45-6789"},
        "employer": {"name": "ACME Inc.", "ein": "12-3456789", "state": "CA"},
        "amounts": {
            "wages": wages,
            "federal_withholding": 12_000,
            "state_withholding": 3_000,
            "social_security_wages": wages,
            "social_security_tax": ss_rate * wages,
            "medicare_wages": wages,
            "medicare_tax": medicare_rate * wages,
        },
        "flags": {"ocr_quality": 0.95},
        "meta": {"source_files": [f"w2_clean_{tax_year}.pdf"]},
    }


def base_1099_int_document(tax_year: int = 2024) -> Dict[str, Any]:
    """Return a clean 1099-INT document that should not trigger rules."""
    return {
        "doc_id": f"1099-clean-{tax_year}",
        "doc_type": "1099-INT",
        "tax_year": tax_year,
        "payer": {"name": "Big Bank, N.A.", "tin": "12-3456789"},
        "recipient": {"name": "John Doe", "tin": "123-45-6789"},
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
        "meta": {"source_files": [f"1099_clean_{tax_year}.pdf"]},
    }


def perturb_w2_zero_fed_withholding(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Set wages > 0 and federal_withholding = 0 to trigger W2_ZERO_FED_WITHHOLDING."""
    mutated = copy.deepcopy(doc)
    amounts = mutated.setdefault("amounts", {})
    amounts["wages"] = max(50_000, amounts.get("wages", 0))
    amounts["federal_withholding"] = 0
    return mutated


def perturb_w2_bad_ssn(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Make taxpayer.ssn invalid to trigger W2_MISSING_TAXPAYER_SSN."""
    mutated = copy.deepcopy(doc)
    taxpayer = mutated.setdefault("taxpayer", {})
    taxpayer["ssn"] = "123-45-67"
    return mutated


def perturb_w2_wrong_social_security_tax(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Alter social security tax to break the expected rate tolerance."""
    mutated = copy.deepcopy(doc)
    amounts = mutated.setdefault("amounts", {})
    wages = amounts.get("social_security_wages", 0) or amounts.get("wages", 0) or 50_000
    amounts["social_security_wages"] = wages
    amounts["social_security_tax"] = 0  # well outside tolerance
    return mutated


def perturb_w2_wrong_medicare_tax(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Alter medicare tax to break the expected rate tolerance."""
    mutated = copy.deepcopy(doc)
    amounts = mutated.setdefault("amounts", {})
    wages = amounts.get("medicare_wages", 0) or amounts.get("wages", 0) or 50_000
    amounts["medicare_wages"] = wages
    amounts["medicare_tax"] = 0  # well outside tolerance
    return mutated


def perturb_int_zero_interest_nonzero_withholding(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Set interest_income = 0 and withholding > 0."""
    mutated = copy.deepcopy(doc)
    amounts = mutated.setdefault("amounts", {})
    amounts["interest_income"] = 0.0
    amounts["federal_tax_withheld"] = 500.0
    return mutated


def perturb_int_large_interest_no_withholding(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Set high interest and zero withholding."""
    mutated = copy.deepcopy(doc)
    amounts = mutated.setdefault("amounts", {})
    amounts["interest_income"] = 15_000.0
    amounts["federal_tax_withheld"] = 0.0
    return mutated


def perturb_int_negative_amount(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Introduce negative value to trigger data quality rule."""
    mutated = copy.deepcopy(doc)
    amounts = mutated.setdefault("amounts", {})
    amounts["tax_exempt_interest"] = -50.0
    return mutated


def perturb_int_bad_recipient_tin(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Make recipient TIN invalid."""
    mutated = copy.deepcopy(doc)
    recipient = mutated.setdefault("recipient", {})
    recipient["tin"] = "123-45-67"
    return mutated


def _load_rules(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or []


def generate_w2_scenarios(tax_year: int = 2024) -> List[Dict[str, Any]]:
    """Generate synthetic W-2 scenarios with expected findings."""
    rules = _load_rules(Path(__file__).resolve().parent.parent / "rules" / "w2.yaml")
    context = get_context_for_year(tax_year)

    clean = base_w2_document(tax_year)
    scenarios_docs = [
        clean,
        perturb_w2_zero_fed_withholding(clean),
        perturb_w2_bad_ssn(clean),
        perturb_w2_wrong_social_security_tax(clean),
        perturb_w2_wrong_medicare_tax(clean),
    ]

    scenarios: List[Dict[str, Any]] = []
    for doc in scenarios_docs:
        findings = apply_rules(doc, rules, context)
        scenarios.append({"doc": doc, "findings": findings})
    return scenarios


def generate_1099_int_scenarios(tax_year: int = 2024) -> List[Dict[str, Any]]:
    """Generate synthetic 1099-INT scenarios with expected findings."""
    rules = _load_rules(Path(__file__).resolve().parent.parent / "rules" / "1099_int.yaml")
    context = get_context_for_year(tax_year)

    clean = base_1099_int_document(tax_year)
    scenarios_docs = [
        clean,
        perturb_int_zero_interest_nonzero_withholding(clean),
        perturb_int_large_interest_no_withholding(clean),
        perturb_int_negative_amount(clean),
        perturb_int_bad_recipient_tin(clean),
    ]

    scenarios: List[Dict[str, Any]] = []
    for doc in scenarios_docs:
        findings = apply_rules(doc, rules, context)
        scenarios.append({"doc": doc, "findings": findings})
    return scenarios


def write_jsonl(path: str | Path, scenarios: Iterable[Dict[str, Any]]) -> None:
    """Write scenarios to a JSONL file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for scenario in scenarios:
            handle.write(json.dumps(scenario))
            handle.write("\n")
