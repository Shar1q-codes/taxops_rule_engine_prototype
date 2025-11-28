"""Production-grade rule engine for TaxOps."""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Mapping, Optional

try:  # pragma: no cover - support running as script/module
    from .registry import RuleRegistry, build_default_registry
except ImportError:  # pragma: no cover - fallback for direct execution
    from registry import RuleRegistry, build_default_registry


class RuleEngineError(Exception):
    """Raised when rule evaluation cannot proceed."""


def _get_path(data: Mapping[str, Any], path: str, default: Any = None) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return default
        current = current[part]
    return current


def _as_number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _pct_diff(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return abs(a - b) / abs(b)


def _re_match(pattern: str, value: Any) -> bool:
    return bool(re.match(pattern, str(value or "").strip()))


def _is_valid_ssn(value: Any) -> bool:
    return _re_match(r"^\d{3}-?\d{2}-?\d{4}$", value)


def _is_valid_ein(value: Any) -> bool:
    return _re_match(r"^\d{2}-?\d{7}$", value)


def _within_tolerance(actual: float, expected: float, tolerance: float) -> bool:
    return abs(actual - expected) <= tolerance


class RuleEngine:
    """Evaluate YAML-defined rules against normalized tax documents."""

    def __init__(self, registry: Optional[RuleRegistry] = None) -> None:
        self.registry = registry or build_default_registry()

    def evaluate(
        self,
        document: Mapping[str, Any],
        *,
        form_type: Optional[str] = None,
        tax_year: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if not isinstance(document, Mapping):
            raise RuleEngineError("document must be a mapping")

        resolved_form = (form_type or document.get("doc_type") or document.get("form_type") or "").upper()
        resolved_year = tax_year or document.get("tax_year")
        if not resolved_form:
            raise RuleEngineError("document missing doc_type/form_type")

        year_params = self.registry.get_year_params(resolved_year)
        rules = self.registry.get_rules(resolved_form)

        env = self._build_environment(document, resolved_form, resolved_year, year_params)

        issues: List[Dict[str, Any]] = []
        for rule in rules:
            if not self._rule_matches_year(rule, resolved_year):
                continue
            condition = (rule.get("condition") or {}).get("expr")
            if not condition:
                continue
            if self._evaluate_expr(condition, env):
                issues.append(self._build_issue(rule, env, resolved_form, resolved_year))
        return issues

    def _rule_matches_year(self, rule: Mapping[str, Any], tax_year: Optional[int]) -> bool:
        years = rule.get("tax_years")
        if not years:
            return True
        try:
            allowed = {int(y) for y in years}
        except Exception:
            return True
        if tax_year is None:
            return False
        return tax_year in allowed

    def _build_environment(
        self,
        document: Mapping[str, Any],
        form_type: str,
        tax_year: Optional[int],
        year_params: Mapping[str, Any],
    ) -> Dict[str, Any]:
        amounts = document.get("amounts") or {}
        employer = document.get("employer") or {}
        taxpayer = document.get("taxpayer") or {}
        flags = document.get("flags") or {}
        payer = document.get("payer") or document.get("payer_info") or document.get("payer_details") or {}

        env: Dict[str, Any] = {
            "doc": document,
            "form_type": form_type,
            "tax_year": tax_year,
            "year_params": year_params,
            "amounts": amounts,
            "employer": employer,
            "taxpayer": taxpayer,
            "payer": payer,
            "flags": flags,
            # Scalar aliases
            "wages": _as_number(amounts.get("wages")),
            "federal_withholding": _as_number(amounts.get("federal_withholding")),
            "state_withholding": _as_number(amounts.get("state_withholding")),
            "social_security_wages": _as_number(amounts.get("social_security_wages")),
            "social_security_tax": _as_number(amounts.get("social_security_tax")),
            "medicare_wages": _as_number(amounts.get("medicare_wages")),
            "medicare_tax": _as_number(amounts.get("medicare_tax")),
            "taxpayer_ssn": taxpayer.get("ssn"),
            "employer_ein": employer.get("ein"),
            "employer_state": employer.get("state"),
            "payer_tin": payer.get("tin") or payer.get("ein"),
            "payer_state": payer.get("state"),
            "ocr_quality": _as_number(flags.get("ocr_quality"), 1.0),
            # Helpers
            "get": lambda path, default=None: _get_path(document, path, default),
            "get_amount": lambda name, default=0.0: _as_number(amounts.get(name, default)),
            "missing": lambda value: value is None or str(value).strip() == "",
            "exists": lambda path: _get_path(document, path) not in (None, ""),
            "pct_diff": _pct_diff,
            "within_tolerance": _within_tolerance,
            "is_valid_ssn": _is_valid_ssn,
            "is_valid_ein": _is_valid_ein,
            "re_match": _re_match,
            "as_number": _as_number,
            "min": min,
            "max": max,
            "abs": abs,
            "round": round,
        }
        return env

    def _evaluate_expr(self, expr: str, env: Dict[str, Any]) -> bool:
        try:
            return bool(eval(expr, {"__builtins__": {}}, env))
        except Exception:
            return False

    def _build_issue(
        self,
        rule: Mapping[str, Any],
        env: Mapping[str, Any],
        form_type: str,
        tax_year: Optional[int],
    ) -> Dict[str, Any]:
        citations = rule.get("references") or []
        fields = rule.get("fields") or []
        severity = (rule.get("severity") or "warning").lower()
        description = rule.get("description") or rule.get("name") or ""
        try:
            message = description.format(**env)
        except Exception:
            message = description

        issue = {
            "id": rule.get("id"),
            "name": rule.get("name"),
            "form_type": form_type,
            "severity": severity,
            "message": message,
            "citations": citations,
            "fields": fields,
            "tax_year": tax_year,
            "rule_source": rule.get("_source"),
            "condition": rule.get("condition"),
        }
        if "hint" in rule:
            issue["hint"] = rule["hint"]
        if "category" in rule:
            issue["category"] = rule["category"]
        return issue


# Initialize a singleton rule engine for application use.
rule_engine = RuleEngine()
