import pytest

from auditor.findings import merge_findings, normalize_llm_findings
from auditor.findings import filter_llm_findings_by_doc


def test_normalize_llm_findings_basic():
    llm_finding = {
        "code": "W2_ZERO_FED_WITHHOLDING",
        "category": "WITHHOLDING",
        "severity": "MEDIUM",
        "summary": "s",
        "details": "d",
        "suggested_action": "a",
        "citation_hint": "c",
        "tags": ["W2"],
    }
    result = normalize_llm_findings("doc-123", [llm_finding])
    assert len(result) == 1
    out = result[0]
    assert "finding_id" in out
    assert out["doc_id"] == "doc-123"
    assert out["source"] == "LLM_AUDITOR"
    assert out["confidence"] == 0.8
    for key in llm_finding:
        assert out[key] == llm_finding[key]


def test_normalize_llm_findings_empty():
    assert normalize_llm_findings("doc-123", []) == []


def test_validate_llm_finding_missing_key():
    llm_finding = {
        "code": "W2_ZERO_FED_WITHHOLDING",
        "category": "WITHHOLDING",
        "severity": "MEDIUM",
        "details": "d",
        "suggested_action": "a",
        "citation_hint": "c",
        "tags": ["W2"],
    }
    with pytest.raises(ValueError) as excinfo:
        normalize_llm_findings("doc-123", [llm_finding])
    assert "summary" in str(excinfo.value)


def test_merge_findings_union():
    rule = [{"code": "RULE", "source": "RULE_ENGINE"}]
    llm = [{"code": "LLM", "source": "LLM_AUDITOR"}]
    merged = merge_findings(rule, llm, strategy="union")
    assert len(merged) == 2
    codes = {m["code"] for m in merged}
    assert codes == {"RULE", "LLM"}


def test_merge_findings_no_duplicates():
    rule = [{"code": "W2_ZERO_FED_WITHHOLDING", "source": "RULE_ENGINE"}]
    llm = [{"code": "W2_ZERO_FED_WITHHOLDING", "source": "LLM_AUDITOR"}]
    merged = merge_findings(rule, llm, strategy="no_duplicates")
    assert len(merged) == 2

    llm_same_source = [{"code": "W2_ZERO_FED_WITHHOLDING", "source": "RULE_ENGINE"}]
    merged_dedup = merge_findings(rule, llm_same_source, strategy="no_duplicates")
    assert len(merged_dedup) == 1


def test_merge_findings_invalid_strategy():
    with pytest.raises(ValueError):
        merge_findings([], [], strategy="something_weird")


def test_filter_llm_findings_ssn_present_rejects_missing_ssn():
    doc = {"taxpayer": {"ssn": "123-45-6789"}}
    finding = {
        "code": "W2_MISSING_TAXPAYER_SSN",
        "category": "IDENTIFICATION",
        "severity": "HIGH",
        "summary": "s",
        "details": "d",
        "suggested_action": "a",
        "citation_hint": "c",
        "tags": [],
    }
    filtered = filter_llm_findings_by_doc(doc, [finding])
    assert filtered == []


def test_filter_llm_findings_ssn_missing_keeps_finding():
    doc = {"taxpayer": {"ssn": ""}}
    finding = {
        "code": "W2_MISSING_TAXPAYER_SSN",
        "category": "IDENTIFICATION",
        "severity": "HIGH",
        "summary": "s",
        "details": "d",
        "suggested_action": "a",
        "citation_hint": "c",
        "tags": [],
    }
    filtered = filter_llm_findings_by_doc(doc, [finding])
    assert filtered == [finding]
