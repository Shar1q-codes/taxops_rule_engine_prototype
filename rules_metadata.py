"""Centralized metadata registry for rule codes across all supported forms.

This module builds a metadata map from the on-disk YAML rule definitions so
UI/LLM layers can look up friendly descriptions without impacting rule evaluation.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from .loader import load_all_rules
except ImportError:  # pragma: no cover
    from loader import load_all_rules


def _build_metadata() -> Dict[str, Dict[str, Any]]:
    metadata: Dict[str, Dict[str, Any]] = {}
    for rule in load_all_rules():
        code = rule.get("id") or rule.get("code")
        if not code:
            continue
        rule_type = rule.get("rule_type") or "structural"
        category = rule.get("category") or "other"
        summary = rule.get("summary") or rule.get("description") or rule.get("name") or code
        tags = rule.get("tags") or []
        metadata[code] = {
            "code": code,
            "short_label": summary or code,
            "long_description": rule.get("description") or rule.get("name") or "",
            "category": category,
            "rule_type": rule_type,
            "summary": summary,
            "severity_default": rule.get("severity") or "",
            "tags": list(tags) if isinstance(tags, list) else [],
            "irs_reference": "; ".join(
                f"{ref.get('source', '')} {ref.get('url', '')}".strip()
                for ref in (rule.get("references") or [])
                if isinstance(ref, dict)
            ).strip(),
        }
    return metadata


RULES_METADATA: Dict[str, Dict[str, Any]] = _build_metadata()


def get_rule_metadata(code: str) -> Optional[Dict[str, Any]]:
    """Return metadata dict for a rule code, or None if not found."""
    return RULES_METADATA.get(code)
