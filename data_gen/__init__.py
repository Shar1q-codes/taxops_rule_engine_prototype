"""Synthetic dataset generation for Corallo TaxOps rule engine."""

from .generators import (
    base_1099_int_document,
    base_w2_document,
    generate_1099_int_scenarios,
    generate_w2_scenarios,
    write_jsonl,
)

__all__ = [
    "base_1099_int_document",
    "base_w2_document",
    "generate_1099_int_scenarios",
    "generate_w2_scenarios",
    "write_jsonl",
]
