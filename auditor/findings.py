"""Utilities for normalizing and merging auditor findings."""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, Iterable, List

REQUIRED_KEYS = {
    "code",
    "category",
    "severity",
    "summary",
    "details",
    "suggested_action",
    "citation_hint",
    "tags",
}


Finding = Dict[str, Any]
ValidatorFn = Callable[[Dict[str, Any], Finding], bool]

LLM_FINDING_VALIDATORS: Dict[str, ValidatorFn] = {}


def register_llm_validator(code: str) -> Callable[[ValidatorFn], ValidatorFn]:
    def _wrap(fn: ValidatorFn) -> ValidatorFn:
        LLM_FINDING_VALIDATORS[code] = fn
        return fn

    return _wrap


def validate_llm_finding(finding: Dict[str, Any]) -> None:
    """Validate that a finding from the LLM contains required keys and types."""
    for key in REQUIRED_KEYS:
        if key not in finding:
            raise ValueError(f"Missing required finding key: {key}")
    if not isinstance(finding.get("tags"), list):
        raise ValueError("Finding 'tags' must be a list")


def normalize_llm_findings(
    doc_id: str,
    findings: List[Dict[str, Any]],
    *,
    default_confidence: float = 0.8,
    source: str = "LLM_AUDITOR",
) -> List[Dict[str, Any]]:
    """Normalize LLM findings to include metadata fields aligned with rule engine outputs."""
    normalized: List[Dict[str, Any]] = []
    for finding in findings:
        validate_llm_finding(finding)
        merged = {
            "finding_id": uuid.uuid4().hex,
            "doc_id": doc_id,
            "source": source,
            "confidence": default_confidence,
        }
        merged.update(finding)
        normalized.append(merged)
    return normalized


def merge_findings(
    rule_findings: List[Dict[str, Any]],
    llm_findings: List[Dict[str, Any]],
    *,
    strategy: str = "union",
) -> List[Dict[str, Any]]:
    """Merge deterministic rule findings and LLM findings according to a strategy."""
    allowed = {"union", "rules_only", "llm_only", "no_duplicates"}
    if strategy not in allowed:
        raise ValueError(f"Unknown strategy: {strategy}")

    if strategy == "rules_only":
        return list(rule_findings)
    if strategy == "llm_only":
        return list(llm_findings)

    if strategy == "union":
        return list(rule_findings) + list(llm_findings)

    combined: List[Dict[str, Any]] = list(rule_findings)
    existing = {(f.get("code"), f.get("source")) for f in combined}
    for finding in llm_findings:
        key = (finding.get("code"), finding.get("source"))
        if key not in existing:
            combined.append(finding)
            existing.add(key)
    return combined


@register_llm_validator("W2_MISSING_TAXPAYER_SSN")
def validate_w2_missing_taxpayer_ssn(doc: Dict[str, Any], finding: Finding) -> bool:
    """
    LLM sometimes flags missing SSN even when taxpayer.ssn is present.
    Return False (reject) if SSN is clearly present and non-empty.
    """
    taxpayer = doc.get("taxpayer") or {}
    ssn = (taxpayer.get("ssn") or "").strip()
    if ssn:
        return False
    return True


def filter_llm_findings_by_doc(
    doc: Dict[str, Any],
    llm_findings: Iterable[Finding],
) -> List[Finding]:
    """
    Apply code-specific validators to LLM findings using the structured doc.
    - If a validator is registered for finding['code']:
        - keep the finding only if validator(doc, finding) returns True.
    - If no validator is registered, keep the finding as-is.
    """
    filtered: List[Finding] = []
    for f in llm_findings:
        code = f.get("code")
        validator = LLM_FINDING_VALIDATORS.get(code)
        if validator is None:
            filtered.append(f)
            continue
        try:
            if validator(doc, f):
                filtered.append(f)
        except Exception:
            filtered.append(f)
    return filtered
