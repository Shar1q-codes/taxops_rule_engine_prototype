"""CLI for converting anomaly JSONL into Auditor LLM training pairs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from training_prep.formatter import example_from_record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare Auditor LLM training data from anomaly JSONL.")
    parser.add_argument("--input", required=True, help="Input anomalies JSONL path.")
    parser.add_argument("--output", required=True, help="Output training JSONL path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    count = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with input_path.open("r", encoding="utf-8") as infile, output_path.open("w", encoding="utf-8") as outfile:
        for line in infile:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                example = example_from_record(record)
                outfile.write(json.dumps(example, ensure_ascii=False))
                outfile.write("\n")
                count += 1
            except Exception as exc:  # pragma: no cover - simple guard
                print(f"Skipping malformed line: {exc}", file=sys.stderr)
                continue

    print(f"Wrote {count} training examples to {output_path}")


if __name__ == "__main__":
    main()
