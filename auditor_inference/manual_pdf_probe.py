"""CLI utility to probe PDFs using the existing extraction pipeline and rule engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from auditor_inference.document_extraction import parse_document
from engine import RuleEngine


def print_basic_info(doc: Dict[str, Any]) -> None:
    print("=== Basic identification ===")
    print(f"doc_type: {doc.get('doc_type') or doc.get('form_type')}")
    print(f"tax_year: {doc.get('tax_year')}")
    payer = doc.get("employer") or doc.get("payer") or {}
    recipient = doc.get("employee") or doc.get("taxpayer") or doc.get("recipient") or {}
    print(f"payer_tin: {payer.get('ein') or payer.get('tin')}")
    print(f"recipient_tin: {recipient.get('ssn') or recipient.get('tin')}")
    meta = doc.get("meta") or {}
    if "ocr_quality" in doc or "ocr_quality" in meta:
        print(f"ocr_quality: {doc.get('ocr_quality') or meta.get('ocr_quality')}")
    if meta:
        print(f"meta: {json.dumps(meta, ensure_ascii=False)}")


def print_numeric_fields(doc: Dict[str, Any]) -> None:
    print("\n=== Key numeric fields ===")
    numeric_items = []

    def collect_numeric(prefix: str, data: Dict[str, Any]):
        for k, v in data.items():
            if isinstance(v, (int, float)):
                numeric_items.append((f"{prefix}{k}", v))

    amounts = doc.get("amounts") or {}
    collect_numeric("amounts.", amounts)
    wages = doc.get("wages") or {}
    collect_numeric("wages.", wages)
    state = doc.get("state") or {}
    collect_numeric("state.", state)

    numeric_items = sorted(numeric_items)[:20]
    for k, v in numeric_items:
        print(f"{k}: {v}")


def print_state_items(doc: Dict[str, Any]) -> None:
    state_items = doc.get("state_items") or []
    if not state_items:
        return
    print("\n=== State items ===")
    for idx, item in enumerate(state_items, start=1):
        if not isinstance(item, dict):
            continue
        print(
            f"[{idx}] state={item.get('state_code') or item.get('state')} "
            f"id={item.get('state_id_number') or ''} "
            f"withheld={item.get('state_tax_withheld')}"
        )


def print_findings(doc: Dict[str, Any]) -> None:
    engine = RuleEngine()
    findings = engine.evaluate(doc, form_type=doc.get("doc_type") or doc.get("form_type"), tax_year=doc.get("tax_year"))
    print("\n=== Findings ===")
    if not findings:
        print("Document is clean (no findings).")
        return
    for f in findings:
        print(f"{f.get('id') or f.get('code')} [{f.get('severity')}] {f.get('message') or f.get('description')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual PDF probe using extraction and rule engine.")
    parser.add_argument("pdf_path", help="Path to PDF file to probe.")
    parser.add_argument("--dump-json", action="store_true", help="Print the normalized JSON document.")
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path).expanduser().resolve()
    if not pdf_path.exists() or not pdf_path.is_file():
        raise SystemExit(f"File not found: {pdf_path}")

    doc = parse_document(pdf_path)

    print_basic_info(doc)
    print_numeric_fields(doc)
    print_state_items(doc)

    if args.dump_json:
        print("\n=== Normalized JSON ===")
        print(json.dumps(doc, indent=2, ensure_ascii=False))

    print_findings(doc)


if __name__ == "__main__":
    main()
