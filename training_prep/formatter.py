"""Formatting helpers to turn anomaly records into LLM training pairs."""

from __future__ import annotations

import json
from typing import Any, Dict, List

KEEP_FINDING_KEYS = [
    "code",
    "category",
    "severity",
    "summary",
    "details",
    "suggested_action",
    "citation_hint",
    "tags",
]


def compress_finding(finding: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reduce a raw rule-engine finding to a stable subset of keys suitable
    for LLM training (no IDs, no source, no confidence).
    """
    return {key: finding.get(key) for key in KEEP_FINDING_KEYS if key in finding}


def format_auditor_prompt(doc: Dict[str, Any]) -> str:
    """
    Build the 'input' prompt string for the Auditor LLM.

    The prompt MUST:
      - Clearly set the role: Corallo TaxOps Auditor.
      - Indicate the doc_type and tax_year if present.
      - Embed the document as pretty-printed JSON under a 'DOCUMENT:' section.
      - Instruct the model to return ONLY a JSON array of findings, following
        the compressed finding schema.
    """
    lines = [
        "You are Corallo TaxOps Auditor.",
        "You will receive a structured tax document as JSON.",
        "Your job:",
        "- Read the document.",
        "- Identify any potential issues, anomalies, or missing information.",
        "- Return a JSON array of audit findings.",
        "",
        "Each finding must use this JSON schema (keys only, no extra fields):",
        "- code",
        "- category",
        "- severity",
        "- summary",
        "- details",
        "- suggested_action",
        "- citation_hint",
        "- tags",
    ]

    doc_type = doc.get("doc_type")
    tax_year = doc.get("tax_year")
    if doc_type:
        lines.append("")
        lines.append(f"Document type: {doc_type}")
    if tax_year:
        lines.append(f"Tax year: {tax_year}")

    pretty_doc = json.dumps(doc, indent=2, ensure_ascii=False)
    lines.append("")
    lines.append("DOCUMENT:")
    lines.append(pretty_doc)
    return "\n".join(lines)


def format_auditor_output(findings: List[Dict[str, Any]]) -> str:
    """
    Build the 'output' target string for training.

    This should be a JSON string (minified is fine) representing a list
    of compressed findings.
    """
    compressed = [compress_finding(f) for f in findings]
    return json.dumps(compressed, ensure_ascii=False)


def example_from_record(record: Dict[str, Any]) -> Dict[str, str]:
    """
    Convert a single anomalies record of shape:
      {"doc": {...}, "findings": [...]}
    into a training example of shape:
      {"input": "<prompt>", "output": "<json array>"}
    """
    if "doc" not in record or "findings" not in record:
        raise ValueError("Record must contain 'doc' and 'findings' keys")
    prompt = format_auditor_prompt(record["doc"])
    output = format_auditor_output(record["findings"])
    return {"input": prompt, "output": output}
