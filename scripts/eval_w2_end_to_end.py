"""End-to-end evaluation harness for W-2 audits using audit_document."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Set

# Support running as a script without installing the package
try:
    from auditor_inference.inference import audit_document, load_chunk_index
except ImportError:  # pragma: no cover - runtime convenience
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from auditor_inference.inference import audit_document, load_chunk_index  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = ROOT / "sample_data" / "eval_w2"
CHUNK_INDEX_PATH = ROOT / "sample_data" / "chunk_index.jsonl"

EXPECTED_RULE_CODES: Dict[str, Set[str]] = {
    "w2_zero_withholding.json": {"W2_ZERO_FED_WITHHOLDING"},
    "w2_normal_withholding.json": set(),
    "w2_ein_malformed.json": {"W2_EIN_MALFORMED_OR_MISSING"},
    "w2_ss_wages_mismatch.json": {"W2_SS_WAGES_MISMATCH"},
    "w2_fica_over_cap.json": {"W2_FICA_OVER_CAP", "W2_SOCSEC_WAGE_CAP"},
}


def load_docs() -> List[Path]:
    return sorted(EVAL_DIR.glob("*.json"))


def summarize_codes(findings: List[Dict]) -> Set[str]:
    return {f.get("code") for f in findings if "code" in f}


def main():
    parser = argparse.ArgumentParser(description="Evaluate W-2 audits end-to-end.")
    parser.add_argument("--device", default="cuda", help="Device for local LLM (if used). Default: cuda")
    parser.add_argument("--skip-llm", action="store_true", help="Run in deterministic-only mode.")
    parser.add_argument("--top", type=int, default=5, help="Max findings to display per category.")
    args = parser.parse_args()

    chunk_index = load_chunk_index(CHUNK_INDEX_PATH)
    docs = load_docs()
    if not docs:
        print(f"No evaluation docs found in {EVAL_DIR}")
        return

    print(f"Found {len(docs)} eval docs in {EVAL_DIR}")
    print(f"Chunk index size: {len(chunk_index)} entries")
    print("-" * 60)

    for doc_path in docs:
        doc = json.loads(doc_path.read_text(encoding="utf-8"))
        result = audit_document(
            doc=doc,
            chunk_index_path=str(CHUNK_INDEX_PATH),
            base_model="mistralai/Mistral-7B-v0.1",
            adapter_dir=str(ROOT / "outputs" / "auditor_mistral_lora"),
            device=args.device,
            max_new_tokens=256,
            use_4bit=False,
            skip_llm=args.skip_llm,
        )

        rule_codes = summarize_codes(result.get("rule_findings", []))
        llm_codes = summarize_codes(result.get("llm_findings", []))
        merged_codes = summarize_codes(result.get("merged_findings", []))

        expected = EXPECTED_RULE_CODES.get(doc_path.name)
        status = "PASS"
        if expected is not None and rule_codes != expected:
            status = "FAIL"

        print(f"{status} {doc_path.name} (rule codes: {sorted(rule_codes)})")
        if expected is not None:
            print(f"  expected: {sorted(expected)}")
        if llm_codes:
            print(f"  llm codes: {sorted(list(llm_codes))[: args.top]}")
        if merged_codes:
            print(f"  merged codes: {sorted(list(merged_codes))[: args.top]}")
        print("-" * 60)


if __name__ == "__main__":
    main()
