"""Production-grade rule engine for TaxOps."""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Mapping, Optional

try:  # pragma: no cover - support running as script/module
    from .registry import RuleRegistry, build_default_registry
except ImportError:  # pragma: no cover - fallback for direct execution
    from registry import RuleRegistry, build_default_registry
try:  # pragma: no cover - support running as script/module
    from .rules_metadata import get_rule_metadata
except ImportError:  # pragma: no cover - fallback for direct execution
    from rules_metadata import get_rule_metadata


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
    if value is None:
        return False
    ssn = str(value).strip()
    if not re.fullmatch(r"\d{3}-\d{2}-\d{4}", ssn):
        return False
    area, group, serial = ssn.split("-")
    if area in {"000", "666", "999"}:
        return False
    if group == "00" or serial == "0000":
        return False
    if ssn == "999-99-9999":
        return False
    return True


def _is_valid_ein(value: Any) -> bool:
    if value is None:
        return False
    raw = str(value).strip()
    if not re.fullmatch(r"\d{2}-?\d{7}", raw):
        return False
    digits = raw.replace("-", "")
    if not digits.isdigit() or len(digits) != 9:
        return False
    if digits == "000000000" or digits == "999999999":
        return False
    if digits[:2] in {"00", "99"}:
        return False
    return True


def _plausible_ein_checksum(value: Any) -> bool:
    """
    Basic EIN heuristic check: rejects repeated digits placeholders.
    This is intentionally lightweight and only used for warnings.
    """
    if not _is_valid_ein(value):
        return False
    digits = re.sub(r"\D", "", str(value))
    if len(set(digits)) == 1:
        return False
    return True


def _within_tolerance(actual: float, expected: float, tolerance: float) -> bool:
    try:
        tol = float(tolerance)
    except Exception:
        tol = 0.0
    return abs(actual - expected) <= tol


def _make_finding(
    *,
    rule: Mapping[str, Any],
    message: str,
    form_type: str,
    tax_year: Optional[int],
    citations: List[Any],
    fields: List[Any],
    rule_source: Any,
    condition: Any,
) -> Dict[str, Any]:
    severity = (rule.get("severity") or "warning").lower()
    code = rule.get("id") or rule.get("code")
    rule_type = (rule.get("rule_type") or "structural") or "structural"
    category = (rule.get("category") or "other") or "other"
    summary = rule.get("summary") or rule.get("name") or message or code
    tags = rule.get("tags") or []
    extras = rule.get("extras") or {}
    condition_expr = condition.get("expr") if isinstance(condition, Mapping) else condition
    field_paths = rule.get("field_paths")
    if not isinstance(field_paths, list):
        field_paths = list(fields) if isinstance(fields, list) else []

    finding = {
        "id": code,
        "code": code,
        "name": rule.get("name"),
        "form_type": form_type,
        "doc_type": form_type or "UNKNOWN",
        "severity": severity,
        "rule_type": str(rule_type),
        "category": category,
        "summary": summary,
        "message": message,
        "citations": citations,
        "fields": fields,
        "field_paths": field_paths,
        "tags": list(tags) if isinstance(tags, list) else [],
        "tax_year": tax_year,
        "rule_source": rule_source,
        "condition": condition_expr,
        "extras": extras if isinstance(extras, Mapping) else {},
    }
    if "hint" in rule:
        finding["hint"] = rule["hint"]
    return finding


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
        if isinstance(resolved_year, str):
            try:
                resolved_year = int(resolved_year)
            except ValueError:
                resolved_year = tax_year or document.get("tax_year")
        if not resolved_form:
            raise RuleEngineError("document missing doc_type/form_type")

        year_params = self.registry.get_year_params(resolved_year)
        rules = self.registry.get_rules(resolved_form)

        env = self._build_environment(
            document,
            resolved_form,
            resolved_year,
            year_params,
            supported_years=self.registry.supported_years,
        )

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
        *,
        supported_years: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        amounts = document.get("amounts") or {}
        employer = document.get("employer") or {}
        employee = document.get("employee") or {}
        taxpayer = document.get("taxpayer") or employee
        recipient = document.get("recipient") or {}
        flags = document.get("flags") or {}
        payer = document.get("payer") or document.get("payer_info") or document.get("payer_details") or {}
        supported_years = list(supported_years) if supported_years is not None else []

        wages_value = _as_number(amounts.get("wages", _get_path(document, "wages.wages_tips_other", 0)))
        federal_withholding = _as_number(
            amounts.get(
                "federal_withholding",
                _get_path(document, "wages.federal_income_tax_withheld", _get_path(document, "amounts.box_4_federal_income_tax_withheld", 0)),
            )
        )
        state_withholding = _as_number(
            amounts.get("state_withholding", _get_path(document, "state.state_tax_withheld", 0))
        )
        social_security_wages_val = _as_number(
            amounts.get("social_security_wages", _get_path(document, "wages.social_security_wages", 0))
        )
        social_security_tax_val = _as_number(
            amounts.get("social_security_tax", _get_path(document, "wages.social_security_tax_withheld", 0))
        )
        medicare_wages_val = _as_number(
            amounts.get("medicare_wages", _get_path(document, "wages.medicare_wages", 0))
        )
        medicare_tax_val = _as_number(
            amounts.get("medicare_tax", _get_path(document, "wages.medicare_tax_withheld", 0))
        )

        env: Dict[str, Any] = {
            "doc": document,
            "form_type": form_type,
            "tax_year": tax_year,
            "tax_quarter": document.get("tax_quarter"),
            "year_params": year_params,
            "amounts": amounts,
            "employer": employer,
            "taxpayer": taxpayer,
            "employee": employee,
            "recipient": recipient,
            "payer": payer,
            "flags": flags,
            # Scalar aliases
            "wages": wages_value,
            "federal_withholding": federal_withholding,
            "state_withholding": state_withholding,
            "social_security_wages": social_security_wages_val,
            "social_security_tax": social_security_tax_val,
            "medicare_wages": medicare_wages_val,
            "medicare_tax": medicare_tax_val,
            "taxpayer_ssn": taxpayer.get("ssn"),
            "employee_ssn": employee.get("ssn"),
            "recipient_tin": recipient.get("tin") or recipient.get("ssn"),
            "recipient_ssn": recipient.get("ssn"),
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
            "ein_checksum_ok": _plausible_ein_checksum,
            "re_match": _re_match,
            "as_number": _as_number,
            "min": min,
            "max": max,
            "abs": abs,
            "round": round,
            "sum": sum,
            "len": len,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "any": any,
            "all": all,
            "supported_years": supported_years,
        }
        return env

    def _evaluate_expr(self, expr: str, env: Dict[str, Any]) -> bool:
        try:
            safe_globals: Dict[str, Any] = {"__builtins__": {}}
            safe_globals.update(env)
            return bool(eval(expr, safe_globals, env))
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
        description = rule.get("description") or rule.get("name") or ""
        try:
            message = description.format(**env)
        except Exception:
            message = description
        return _make_finding(
            rule=rule,
            message=message,
            form_type=form_type,
            tax_year=tax_year,
            citations=citations,
            fields=fields,
            rule_source=rule.get("_source"),
            condition=rule.get("condition"),
        )


# Initialize a singleton rule engine for application use.
rule_engine = RuleEngine()
