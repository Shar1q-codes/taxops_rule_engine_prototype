"""Document extraction utilities for PDFs, images, and JSON tax documents.

Dependencies for PDF extraction (install as needed):
  pip install pdfplumber  # preferred
  # or
  pip install pypdf

Dependencies for image OCR (install as needed):
  pip install pillow pytesseract
"""

from __future__ import annotations

import json
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List


def load_json_document(path: str | Path) -> Dict[str, Any]:
    """Load a JSON document file."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as handle:
        doc = json.load(handle)
    if not isinstance(doc, dict):
        raise ValueError(f"Expected JSON object in {p}")
    return doc


def extract_text_from_pdf(path_or_stream: str | Path | BytesIO) -> str:
    """Extract text from PDF using pdfplumber or PyPDF2."""
    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(path_or_stream) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore

            reader = PdfReader(path_or_stream)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError as exc:
            raise ImportError("Install pdfplumber or pypdf/PyPDF2 for PDF extraction.") from exc


def extract_structured_fields(text: str) -> Dict[str, Any]:
    """Very lightweight heuristic extraction for SSN/EIN/tax year mentions."""
    fields: Dict[str, Any] = {}
    ssn_match = re.search(r"\b(\d{3}-\d{2}-\d{4})\b", text)
    ein_match = re.search(r"\b(\d{2}-\d{7})\b", text)
    year_match = re.search(r"\b(20\d{2})\b", text)
    if ssn_match:
        fields["taxpayer"] = {"ssn": ssn_match.group(1)}
    if ein_match:
        fields.setdefault("employer", {})["ein"] = ein_match.group(1)
    if year_match:
        fields["tax_year"] = int(year_match.group(1))
    return fields


def extract_clause_indicators(text: str) -> List[str]:
    """Detect simple clause indicators (e.g., withholding, exemption)."""
    indicators = []
    lowered = text.lower()
    if "withholding" in lowered:
        indicators.append("withholding")
    if "exempt" in lowered:
        indicators.append("exemption")
    if "penalty" in lowered:
        indicators.append("penalty")
    return indicators


def extract_text_from_image(path: str | Path) -> str:
    """Extract text from common image formats using Tesseract if available."""
    try:
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError("Install pillow and pytesseract for image OCR.") from exc

    with Image.open(path) as img:
        return pytesseract.image_to_string(img)


def extract_text_from_image_bytes(data: bytes) -> str:
    """Extract text from in-memory image bytes."""
    try:
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError("Install pillow and pytesseract for image OCR.") from exc

    with Image.open(BytesIO(data)) as img:
        return pytesseract.image_to_string(img)


def parse_document(path: str | Path) -> Dict[str, Any]:
    """Parse PDF/image/JSON into a structured dict with minimal heuristics."""
    p = Path(path)
    if p.suffix.lower() == ".json":
        return load_json_document(p)

    if p.suffix.lower() == ".pdf":
        text = extract_text_from_pdf(p)
        doc: Dict[str, Any] = {"doc_id": p.stem, "doc_type": "UNKNOWN", "raw_text": text}
        doc.update(extract_structured_fields(text))
        doc["clauses"] = extract_clause_indicators(text)
        doc["meta"] = {"source_file": p.name}
        return doc

    if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}:
        text = extract_text_from_image(p)
        doc = {"doc_id": p.stem, "doc_type": "UNKNOWN", "raw_text": text}
        doc.update(extract_structured_fields(text))
        doc["clauses"] = extract_clause_indicators(text)
        doc["meta"] = {"source_file": p.name}
        return doc

    raise ValueError(f"Unsupported document type for {p}")


def parse_document_bytes(filename: str, data: bytes) -> Dict[str, Any]:
    """Parse uploaded bytes using the filename extension for routing."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".json":
        try:
            doc = json.loads(data.decode("utf-8"))
        except Exception as exc:
            raise ValueError("Invalid JSON payload") from exc
        if not isinstance(doc, dict):
            raise ValueError("Expected JSON object as document root.")
        return doc

    if suffix == ".pdf":
        text = extract_text_from_pdf(BytesIO(data))
        doc: Dict[str, Any] = {"doc_id": Path(filename).stem, "doc_type": "UNKNOWN", "raw_text": text}
        doc.update(extract_structured_fields(text))
        doc["clauses"] = extract_clause_indicators(text)
        doc["meta"] = {"source_file": filename}
        return doc

    if suffix in {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}:
        text = extract_text_from_image_bytes(data)
        doc = {"doc_id": Path(filename).stem, "doc_type": "UNKNOWN", "raw_text": text}
        doc.update(extract_structured_fields(text))
        doc["clauses"] = extract_clause_indicators(text)
        doc["meta"] = {"source_file": filename}
        return doc

    raise ValueError(f"Unsupported file type: {suffix or 'unknown'}")
