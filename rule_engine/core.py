"""Deterministic rule engine for structured tax documents."""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, Iterable, List, Mapping, Optional


def get_path(obj: Mapping[str, Any] | None, path: str, default: Any = None) -> Any:
    """Resolve dotted path lookups on nested dictionaries."""
    if obj is None:
        return default
    current: Any = obj
    for key in path.split("."):
        if not isinstance(current, Mapping):
            return default
        if key not in current:
            return default
        current = current[key]
    return current


def stripped(value: Any) -> str:
    """Strip non-digit characters from a string."""
    if value is None:
        return ""
    return re.sub(r"\D", "", str(value))


_IDENT_RE = re.compile(r"\b([A-Za-z_][\w\.]*)\b")
_RESERVED = {"and", "or", "not", "True", "False", "None", "abs", "get", "stripped"}


def build_eval_expr(condition: str) -> str:
    """Convert a dotted-path condition into a safe eval expression."""

    def replacer(match: re.Match[str]) -> str:
        token = match.group(1)
        if token in _RESERVED:
            return token
        if "." in token:
            return f'get(env, "{token}")'
        return token

    return _IDENT_RE.sub(replacer, condition)


def evaluate_condition(condition: str, env: Mapping[str, Any]) -> bool:
    """Evaluate a rule condition against the provided environment."""
    try:
        expr = build_eval_expr(condition)
        allowed = {
            "__builtins__": {},
            "get": lambda obj, path: get_path(obj, path),
            "abs": abs,
            "stripped": stripped,
            "True": True,
            "False": False,
            "None": None,
            "env": env,
        }
        return bool(eval(expr, allowed))
    except Exception:
        return False


def apply_rules(
    document: Optional[Dict[str, Any]],
    rules: Iterable[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Apply deterministic rules to a document and return triggered findings."""
    env: Dict[str, Any] = {}
    if context:
        env.update(context)
    if document:
        env.update(document)

    findings: List[Dict[str, Any]] = []
    doc_type = (document or {}).get("doc_type")

    for rule in rules:
        if not isinstance(rule, Mapping):
            continue
        if rule.get("doc_type") != doc_type:
            continue

        condition = rule.get("condition", "")
        if not condition:
            continue

        if evaluate_condition(condition, env):
            finding = {
                "finding_id": str(uuid.uuid4()),
                "doc_id": (document or {}).get("doc_id"),
                "source": "RULE_ENGINE",
                "code": rule.get("id"),
                "category": rule.get("category"),
                "severity": rule.get("severity"),
                "confidence": 1.0,
                "summary": rule.get("summary"),
                "details": rule.get("details"),
                "suggested_action": rule.get("suggested_action"),
                "citation_hint": rule.get("citation_hint"),
                "tags": rule.get("tags", []),
            }
            findings.append(finding)

    return findings
