"""CLI for generating synthetic anomaly datasets."""

from __future__ import annotations

import argparse
import sys

from data_gen.generators import (
    generate_1099_int_scenarios,
    generate_w2_scenarios,
    write_jsonl,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic anomaly datasets.")
    parser.add_argument("--doc-type", required=True, choices=["W2", "1099-INT"], help="Document type to generate.")
    parser.add_argument("--tax-year", type=int, default=2024, help="Tax year for generation.")
    parser.add_argument("--output", required=True, help="Output JSONL file path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.doc_type == "W2":
        scenarios = generate_w2_scenarios(args.tax_year)
    elif args.doc_type == "1099-INT":
        scenarios = generate_1099_int_scenarios(args.tax_year)
    else:
        print(f"Unsupported doc-type: {args.doc_type}", file=sys.stderr)
        sys.exit(1)

    write_jsonl(args.output, scenarios)
    print(f"Wrote {len(scenarios)} scenarios to {args.output}")


if __name__ == "__main__":
    main()
