import json

import pytest

from training_prep.formatter import (
    compress_finding,
    example_from_record,
    format_auditor_output,
    format_auditor_prompt,
)


def test_compress_finding_drops_dynamic_fields():
    finding = {
        "finding_id": "abc",
        "doc_id": "doc",
        "source": "RULE_ENGINE",
        "confidence": 1.0,
        "code": "W2_ZERO_FED_WITHHOLDING",
        "category": "WITHHOLDING",
        "severity": "MEDIUM",
        "summary": "summary",
        "details": "details",
        "suggested_action": "act",
        "citation_hint": "cite",
        "tags": ["W2"],
    }
    compressed = compress_finding(finding)
    assert "finding_id" not in compressed
    assert "doc_id" not in compressed
    assert "source" not in compressed
    assert "confidence" not in compressed
    for key in ["code", "category", "severity", "summary", "details", "suggested_action", "citation_hint", "tags"]:
        assert compressed[key] == finding[key]


def test_format_auditor_prompt_contains_document_json_and_schema():
    doc = {"doc_type": "W2", "tax_year": 2024, "amounts": {"wages": 100}}
    prompt = format_auditor_prompt(doc)
    assert "Corallo TaxOps Auditor" in prompt
    assert "DOCUMENT:" in prompt
    assert '"doc_type": "W2"' in prompt
    assert '"tax_year": 2024' in prompt
    for key in ["code", "severity", "tags"]:
        assert key in prompt


def test_format_auditor_output_is_valid_json_array():
    findings = [
        {
            "finding_id": "x",
            "code": "ABC",
            "category": "CAT",
            "severity": "LOW",
            "summary": "s",
            "details": "d",
            "suggested_action": "a",
            "citation_hint": "c",
            "tags": [],
        }
    ]
    output = format_auditor_output(findings)
    data = json.loads(output)
    assert isinstance(data, list)
    assert data[0]["code"] == "ABC"
    assert "finding_id" not in data[0]


def test_example_from_record_builds_input_and_output_pair():
    record = {
        "doc": {"doc_type": "W2", "tax_year": 2024, "amounts": {"wages": 100}},
        "findings": [
            {
                "code": "W2_ZERO_FED_WITHHOLDING",
                "category": "WITHHOLDING",
                "severity": "MEDIUM",
                "summary": "s",
                "details": "d",
                "suggested_action": "a",
                "citation_hint": "c",
                "tags": ["W2"],
            }
        ],
    }
    example = example_from_record(record)
    assert "input" in example and "output" in example
    assert "Corallo TaxOps Auditor" in example["input"]
    assert "DOCUMENT:" in example["input"]
    json_output = json.loads(example["output"])
    assert isinstance(json_output, list)
    assert json_output[0]["code"] == "W2_ZERO_FED_WITHHOLDING"


def test_example_from_record_missing_keys_raises():
    with pytest.raises(ValueError):
        example_from_record({"doc": {}})
