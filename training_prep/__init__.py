"""Formatter utilities for preparing Auditor LLM training data."""

from .formatter import (
    compress_finding,
    example_from_record,
    format_auditor_output,
    format_auditor_prompt,
)

__all__ = [
    "compress_finding",
    "example_from_record",
    "format_auditor_output",
    "format_auditor_prompt",
]
