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
import logging
import re
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


def safe_float(val: Any, default: float = 0.0) -> float:
    """Parse a float safely, stripping commas and handling empty values."""
    if val is None:
        return float(default)
    try:
        if isinstance(val, str):
            val = val.replace(",", "").strip()
            if not val:
                return float(default)
        return float(val)
    except Exception:
        return float(default)


def load_json_document(path: str | Path) -> Dict[str, Any]:
    """Load a JSON document file."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as handle:
        doc = json.load(handle)
    if not isinstance(doc, dict):
        raise ValueError(f"Expected JSON object in {p}")
    return doc


def extract_text_from_pdf(path_or_stream: str | Path | BytesIO) -> Tuple[str, bool]:
    """Extract text from PDF using pdfplumber or PyPDF2, with OCR fallback."""
    text = ""
    used_ocr = False
    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(path_or_stream) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except ImportError:
        text = ""
    except Exception as exc:
        logger.warning("pdfplumber extraction failed: %s", exc)
        text = ""

    if not text or len(text.strip()) < 50:
        # Fallback: try PyPDF2 text extraction
        try:
            from PyPDF2 import PdfReader  # type: ignore

            reader = PdfReader(path_or_stream)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            logger.warning("PyPDF2 extraction failed: %s", exc)
            text = ""

    if not text or len(text.strip()) < 50:
        # Last resort: OCR each page if pdf2image + pytesseract are available
        try:
            from pdf2image import convert_from_path, convert_from_bytes  # type: ignore
            from PIL import Image  # type: ignore
            import pytesseract  # type: ignore

            if isinstance(path_or_stream, (str, Path)):
                images = convert_from_path(str(path_or_stream), dpi=200)
            else:
                raw = path_or_stream.read() if hasattr(path_or_stream, "read") else path_or_stream
                images = convert_from_bytes(raw, dpi=200)
            ocr_texts = [pytesseract.image_to_string(img) for img in images]
            text = "\n".join(ocr_texts)
            used_ocr = True
        except Exception as exc:
            logger.warning("OCR extraction failed: %s", exc)
            # If OCR dependencies not available, keep whatever text we have (possibly empty)
            pass

    return text, used_ocr


def extract_structured_fields(text: str) -> Dict[str, Any]:
    """Very lightweight heuristic extraction for SSN/EIN/tax year mentions."""
    fields: Dict[str, Any] = {}
    ssn_match = re.search(r"\b(\d{3}-\d{2}-\d{4})\b", text)
    ein_match = re.search(r"\b(\d{2}-\d{7})\b", text)
    year_match = re.search(r"\b(20\d{2})\b", text)
    if ssn_match:
        fields["employee"] = {"ssn": ssn_match.group(1)}
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


def _blank_w2(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "form_type": "W2",
        "doc_type": "W2",
        "employee": {"first_name": "", "last_name": "", "ssn": ""},
        "employer": {"name": "", "ein": ""},
        "wages": {
            "wages_tips_other": 0.0,
            "federal_income_tax_withheld": 0.0,
            "social_security_wages": 0.0,
            "social_security_tax_withheld": 0.0,
            "medicare_wages": 0.0,
            "medicare_tax_withheld": 0.0,
        },
        "state": {"state_code": "", "state_wages": 0.0, "state_tax_withheld": 0.0},
        "tax_year": None,
        "ocr_quality": 0.5,
    }


def _apply_extracted_fields(doc: Dict[str, Any], extracted: Dict[str, Any]) -> None:
    if not extracted:
        return
    employee = extracted.get("employee") or {}
    employer = extracted.get("employer") or {}
    if "first_name" in employee or "last_name" in employee or "ssn" in employee:
        doc["employee"].update({k: v for k, v in employee.items() if v})
    if employer:
        doc["employer"].update({k: v for k, v in employer.items() if v})
    if "tax_year" in extracted:
        doc["tax_year"] = extracted["tax_year"]


def _assign_ocr_quality(text: str, used_ocr: bool) -> float:
    confidence = 0.9 if text and len(text.strip()) > 80 and not used_ocr else 0.5
    return 1.0 if confidence >= 0.85 else 0.5


def parse_w2_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    """Normalize extracted text into W-2 structured payload."""
    doc = _blank_w2(doc_id)
    extracted = extract_structured_fields(text)
    _apply_extracted_fields(doc, extracted)
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc


def parse_document(path: str | Path) -> Dict[str, Any]:
    """Parse PDF/image/JSON into a structured dict with minimal heuristics."""
    p = Path(path)
    if p.suffix.lower() == ".json":
        return load_json_document(p)

    if p.suffix.lower() == ".pdf":
        text, used_ocr = extract_text_from_pdf(p)
        doc_id = p.stem or uuid.uuid4().hex
        doc = parse_w2_from_text(doc_id, text, used_ocr)
        doc["meta"] = {"source_file": p.name}
        return doc

    if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}:
        text = extract_text_from_image(p)
        doc_id = p.stem or uuid.uuid4().hex
        doc = parse_w2_from_text(doc_id, text, used_ocr=True)
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
        text, used_ocr = extract_text_from_pdf(BytesIO(data))
        doc_id = Path(filename).stem or uuid.uuid4().hex
        doc = parse_w2_from_text(doc_id, text, used_ocr)
        doc["meta"] = {"source_file": filename}
        return doc

    if suffix in {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}:
        text = extract_text_from_image_bytes(data)
        doc_id = Path(filename).stem or uuid.uuid4().hex
        doc = parse_w2_from_text(doc_id, text, used_ocr=True)
        doc["meta"] = {"source_file": filename}
        return doc

    raise ValueError(f"Unsupported file type: {suffix or 'unknown'}")
