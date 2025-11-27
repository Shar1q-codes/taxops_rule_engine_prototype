import json

from data_gen.generators import (
    generate_1099_int_scenarios,
    generate_w2_scenarios,
    write_jsonl,
)


def test_generate_w2_scenarios_includes_clean_and_anomalies():
    scenarios = generate_w2_scenarios(tax_year=2024)
    assert scenarios
    has_clean = any(s["findings"] == [] for s in scenarios)
    has_anomaly = any(s["findings"] for s in scenarios)
    assert has_clean
    assert has_anomaly
    flagged = [
        s
        for s in scenarios
        if any(f["code"] in {"W2_ZERO_FED_WITHHOLDING", "W2_MISSING_TAXPAYER_SSN"} for f in s["findings"])
    ]
    assert flagged


def test_generate_1099_int_scenarios_includes_clean_and_anomalies():
    scenarios = generate_1099_int_scenarios(tax_year=2024)
    assert scenarios
    has_clean = any(s["findings"] == [] for s in scenarios)
    has_anomaly = any(s["findings"] for s in scenarios)
    assert has_clean
    assert has_anomaly
    flagged = [
        s
        for s in scenarios
        if any(
            f["code"]
            in {
                "INT_ZERO_INTEREST_NONZERO_WITHHOLDING",
                "INT_MISSING_RECIPIENT_TIN",
                "INT_NEGATIVE_INTEREST_OR_TAX",
            }
            for f in s["findings"]
        )
    ]
    assert flagged


def test_write_jsonl_creates_valid_lines(tmp_path):
    scenarios = [
        {"doc": {"doc_type": "W2"}, "findings": []},
        {"doc": {"doc_type": "1099-INT"}, "findings": [{"code": "X"}]},
    ]
    output = tmp_path / "out.jsonl"
    write_jsonl(output, scenarios)

    lines = output.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        obj = json.loads(line)
        assert "doc" in obj and "findings" in obj
