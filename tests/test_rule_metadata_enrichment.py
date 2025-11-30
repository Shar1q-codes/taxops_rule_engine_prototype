import json
from pathlib import Path

from engine import RuleEngine


ROOT = Path(__file__).resolve().parent.parent


def _load_doc(name: str) -> dict:
    with (ROOT / "sample_data" / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_rule_findings_include_metadata_and_defaults():
    engine = RuleEngine()
    doc = _load_doc("w2_issues.json")
    findings = engine.evaluate(doc, form_type=doc.get("doc_type"), tax_year=doc.get("tax_year"))

    ssn_issue = next(f for f in findings if f.get("id") == "W2_SSN_FORMAT")
    assert ssn_issue["rule_type"] == "structural"
    assert ssn_issue["category"]
    assert ssn_issue["summary"]
    assert ssn_issue.get("tags") == ["W-2", "identity", "ssn"]

    any_issue = findings[0]
    assert "rule_type" in any_issue
    assert "category" in any_issue
    assert "summary" in any_issue
    assert "tags" in any_issue
