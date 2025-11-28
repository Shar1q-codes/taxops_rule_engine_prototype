import json
import pathlib

try:
    from auditor_inference.run_audit import run_audit  # adjust only if path differs
except Exception:  # pragma: no cover - fallback if function not exposed
    from engine import rule_engine

    def run_audit(doc: dict) -> dict:  # type: ignore
        return {
            "rule_issues": rule_engine.evaluate(
                doc, form_type=doc.get("form_type") or doc.get("doc_type"), tax_year=doc.get("tax_year")
            )
        }

ROOT = pathlib.Path(__file__).resolve().parent


def load_doc(name: str) -> dict:
    path = ROOT / "sample_data" / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main():
    for fname in ["w2_valid.json", "w2_issues.json"]:
        doc = load_doc(fname)
        print(f"\n=== Running audit on {fname} ===")
        result = run_audit(doc)
        rule_issues = result.get("rule_issues", [])
        print(f"Total rule issues: {len(rule_issues)}")
        for issue in rule_issues:
            print(
                "-",
                issue.get("id"),
                "| severity:", issue.get("severity"),
                "| msg:", issue.get("message") or issue.get("description")
            )


if __name__ == "__main__":
    main()
