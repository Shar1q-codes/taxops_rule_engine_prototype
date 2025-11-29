"""Document extraction utilities for PDFs, images, and JSON tax documents.

Dependencies for PDF extraction (install as needed):
  pip install pdfplumber  # preferred
  # or
  pip install pypdf

Dependencies for image OCR (install as needed):
  pip install pillow pytesseract
"""

from __future__ import annotations

import io
import json
import logging
import re
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Tuple
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)

def safe_float(val: Any, default: float = 0.0) -> float:
    """Parse a float safely, stripping commas and handling empty values."""
    if val is None:
        return float(default)
    try:
        if isinstance(val, str):
            cleaned = val.replace("$", "").replace(",", "").strip()
            if cleaned.startswith("(") and cleaned.endswith(")"):
                cleaned = f"-{cleaned[1:-1].strip()}"
            if not cleaned:
                return float(default)
            val = cleaned
        return float(val)
    except Exception:
        logger.warning("Failed to parse numeric value %r; defaulting to %s", val, default)
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
    year_matches = re.findall(r"\b(20\d{2})\b", text)
    if ssn_match:
        fields["employee"] = {"ssn": ssn_match.group(1)}
    if ein_match:
        fields.setdefault("employer", {})["ein"] = ein_match.group(1)
    if year_matches:
        fields["detected_years"] = [int(y) for y in year_matches]
        fields["tax_year"] = int(year_matches[0])
    return fields


def extract_acroform_fields(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Attempt to extract AcroForm field names and values from an interactive / fillable W-2 PDF.
    Returns a flat dict mapping field_name -> string_value.
    """
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:
        logger.warning("Failed to read PDF for AcroForm extraction: %s", exc)
        return {}

    fields: Dict[str, Any] = {}
    try:
        raw_fields = reader.get_fields()
        if not raw_fields:
            return {}
        for name, field in raw_fields.items():
            value = field.get("/V")
            if value is None:
                continue
            if isinstance(value, str):
                fields[name] = value.strip()
            else:
                fields[name] = str(value).strip()
    except Exception as exc:
        logger.warning("Error while extracting AcroForm fields: %s", exc)
        return {}

    return fields


def map_w2_fields_from_form(form_fields: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map common W-2 interactive/form field names into our normalized W-2 structure.
    This is a best-effort mapping for typical interactive W-2 PDFs (e.g., ADP, payroll vendors).
    """

    def get_first(*keys: str, default: str | None = None) -> str | None:
        for k in keys:
            if k in form_fields and str(form_fields[k]).strip():
                return str(form_fields[k]).strip()
        return default

    ssn = get_first("EmployeeSSN", "EmpSSN", "SSN", "f1_8", "SSN_1")
    ein = get_first("EmployerEIN", "EIN", "EmpEIN", "f1_2", "EIN_1")

    def parse_float(val: Any) -> float:
        return safe_float(val, 0.0)

    wages_box1 = parse_float(get_first("WagesTipsOther", "Wages_Tips", "Box1", "W2_Box1"))
    fit_box2 = parse_float(get_first("FedIncomeTaxWithheld", "Box2", "W2_Box2"))
    ss_wages_b3 = parse_float(get_first("SocialSecurityWages", "Box3", "W2_Box3"))
    ss_tax_b4 = parse_float(get_first("SocialSecurityTax", "Box4", "W2_Box4"))
    med_wages_b5 = parse_float(get_first("MedicareWages", "Box5", "W2_Box5"))
    med_tax_b6 = parse_float(get_first("MedicareTax", "Box6", "W2_Box6"))
    state_wages = parse_float(get_first("StateWages", "Box16", "W2_Box16"))
    state_tax = parse_float(get_first("StateIncomeTax", "Box17", "W2_Box17"))

    tax_year_str = get_first("TaxYear", "Year", "W2_Year")
    tax_year = None
    if tax_year_str:
        try:
            tax_year = int(str(tax_year_str).strip())
        except ValueError:
            tax_year = None

    logger.info(
        "W-2 form-field mapping applied: wages_box1=%s, fit=%s, ss_wages=%s",
        wages_box1,
        fit_box2,
        ss_wages_b3,
    )

    return {
        "employee": {
            "ssn": ssn,
        },
        "employer": {
            "ein": ein,
        },
        "wages": {
            "wages_tips_other": wages_box1,
            "federal_income_tax_withheld": fit_box2,
            "social_security_wages": ss_wages_b3,
            "social_security_tax_withheld": ss_tax_b4,
            "medicare_wages": med_wages_b5,
            "medicare_tax_withheld": med_tax_b6,
        },
        "state": {
            "state_wages": state_wages,
            "state_tax_withheld": state_tax,
        },
        "tax_year": tax_year,
    }

def extract_box_value(text: str, label: str) -> float:
    """Extract numeric value following a W-2 box label."""
    pattern = rf"{re.escape(label)}\s*[:\-]?\s*\$?([\d,]+(?:\.\d+)?)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return 0.0
    return safe_float(match.group(1), 0.0)


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
        "ocr_quality": 1.0,
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
    return 0.7 if used_ocr else 1.0


def _extract_wage_boxes(text: str) -> Dict[str, float]:
    label_sets = {
        ("Box 1", "Box1", "1", "1."): ("wages", "wages_tips_other"),
        ("Box 2", "Box2", "2", "2."): ("wages", "federal_income_tax_withheld"),
        ("Box 3", "Box3", "3", "3."): ("wages", "social_security_wages"),
        ("Box 4", "Box4", "4", "4."): ("wages", "social_security_tax_withheld"),
        ("Box 5", "Box5", "5", "5."): ("wages", "medicare_wages"),
        ("Box 6", "Box6", "6", "6."): ("wages", "medicare_tax_withheld"),
        ("Box 16", "Box16", "16", "16."): ("state", "state_wages"),
        ("Box 17", "Box17", "17", "17."): ("state", "state_tax_withheld"),
    }
    results: Dict[str, float] = {}
    for labels, (section, key) in label_sets.items():
        val = 0.0
        for label in labels:
            val = extract_box_value(text, label)
            if val > 0:
                break
        if val <= 0:
            # Try line-based pattern like "1 Wages, tips, other compensation 50,000.00"
            box_num = re.sub(r"\D", "", labels[0]) or labels[0]
            pattern = rf"^{box_num}\s+[A-Za-z, \-/]+?\s+\$?([\d,]+(?:\.\d+)?)"
            match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
            if match:
                val = safe_float(match.group(1), 0.0)
        if val > 0:
            results[f"{section}.{key}"] = val
    return results


def _fallback_numeric_by_keyword(text: str, keyword: str) -> float:
    pattern = rf"{keyword}.*?\$?([\d,]+(?:\.\d+)?)"
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return safe_float(match.group(1), 0.0)
    return 0.0


def _apply_fallback_amounts(doc: Dict[str, Any], text: str) -> None:
    wages = doc.get("wages") or {}
    mappings = {
        "wages_tips_other": ["wages", "wages tips", "box 1"],
        "federal_income_tax_withheld": ["federal income tax", "federal withholding", "box 2"],
        "social_security_wages": ["social security wages", "box 3"],
        "social_security_tax_withheld": ["social security tax", "box 4"],
        "medicare_wages": ["medicare wages", "box 5"],
        "medicare_tax_withheld": ["medicare tax", "box 6"],
    }
    for field, keywords in mappings.items():
        if safe_float(wages.get(field), 0.0) > 0.0:
            continue
        for kw in keywords:
            val = _fallback_numeric_by_keyword(text, kw)
            if val > 0:
                wages[field] = val
                break
    doc["wages"] = wages


def _populate_wages_from_text(doc: Dict[str, Any], text: str) -> None:
    values = _extract_wage_boxes(text)
    for dotted, val in values.items():
        section, key = dotted.split(".", 1)
        if section not in doc or not isinstance(doc[section], dict):
            continue
        doc[section][key] = val


def _wages_missing(doc: Dict[str, Any]) -> bool:
    wages = doc.get("wages") or {}
    required_keys = [
        "wages_tips_other",
        "federal_income_tax_withheld",
        "social_security_wages",
        "social_security_tax_withheld",
        "medicare_wages",
        "medicare_tax_withheld",
    ]
    return any(safe_float(wages.get(k, 0.0), 0.0) <= 0.0 for k in required_keys)


def _log_missing_fields(doc: Dict[str, Any]) -> None:
    wages = doc.get("wages") or {}
    state = doc.get("state") or {}
    wages_present = safe_float(wages.get("wages_tips_other"), 0.0) > 0.0
    if wages_present:
        checks = [
            ("wages.federal_income_tax_withheld", wages.get("federal_income_tax_withheld")),
            ("wages.social_security_wages", wages.get("social_security_wages")),
            ("wages.social_security_tax_withheld", wages.get("social_security_tax_withheld")),
            ("wages.medicare_wages", wages.get("medicare_wages")),
            ("wages.medicare_tax_withheld", wages.get("medicare_tax_withheld")),
        ]
        for field, value in checks:
            if safe_float(value, 0.0) <= 0.0:
                logger.warning("Missing field: %s", field)

    state_code = state.get("state_code") or ""
    if state_code.strip():
        for field, value in [
            ("state.state_wages", state.get("state_wages")),
            ("state.state_tax_withheld", state.get("state_tax_withheld")),
        ]:
            if safe_float(value, 0.0) <= 0.0:
                logger.warning("Missing field: %s", field)


def _merge_form_mapping(doc: Dict[str, Any], mapped: Dict[str, Any]) -> None:
    if not mapped:
        return
    doc["employee"]["ssn"] = doc["employee"].get("ssn") or mapped.get("employee", {}).get("ssn") or ""
    doc["employer"]["ein"] = doc["employer"].get("ein") or mapped.get("employer", {}).get("ein") or ""
    for key, val in (mapped.get("wages") or {}).items():
        if doc["wages"].get(key) in (None, 0, 0.0, "") and val not in (None, 0, 0.0, ""):
            doc["wages"][key] = val
    for key, val in (mapped.get("state") or {}).items():
        if doc["state"].get(key) in (None, 0, 0.0, "") and val not in (None, 0, 0.0, ""):
            doc["state"][key] = val
    if (doc.get("tax_year") in (None, 0, "")) and mapped.get("tax_year"):
        doc["tax_year"] = mapped["tax_year"]
    # If form provided numeric wages, treat as high confidence.
    if any(v > 0 for v in (mapped.get("wages") or {}).values()):
        doc["ocr_quality"] = 1.0


def _merge_docs(primary: Dict[str, Any], secondary: Dict[str, Any]) -> Dict[str, Any]:
    """Fill missing/empty values in primary with values from secondary."""
    merged = primary
    for section in ("employee", "employer", "wages", "state"):
        if section not in merged or not isinstance(merged[section], dict):
            merged[section] = {}
        if section in secondary and isinstance(secondary[section], dict):
            for key, val in secondary[section].items():
                current = merged[section].get(key)
                if (current in ("", None) or safe_float(current, 0.0) == 0.0) and val not in ("", None):
                    merged[section][key] = val
    if merged.get("tax_year") in (None, "", 0) and secondary.get("tax_year"):
        merged["tax_year"] = secondary["tax_year"]
    return merged


def parse_w2_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    """Normalize extracted text into W-2 structured payload."""
    doc = _blank_w2(doc_id)
    extracted = extract_structured_fields(text)
    _apply_extracted_fields(doc, extracted)
    _populate_wages_from_text(doc, text)
    _apply_fallback_amounts(doc, text)
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc


def _force_pdf_ocr(path_or_stream: str | Path | BytesIO) -> str:
    """Run OCR on a PDF source regardless of prior extraction attempts."""
    try:
        from pdf2image import convert_from_path, convert_from_bytes  # type: ignore
        import pytesseract  # type: ignore

        if isinstance(path_or_stream, (str, Path)):
            images = convert_from_path(str(path_or_stream), dpi=200)
        else:
            raw = path_or_stream.read() if hasattr(path_or_stream, "read") else path_or_stream
            images = convert_from_bytes(raw, dpi=200)
        ocr_texts = [pytesseract.image_to_string(img) for img in images]
        return "\n".join(ocr_texts)
    except Exception as exc:
        logger.warning("Forced OCR failed: %s", exc)
        return ""


def parse_document(path: str | Path) -> Dict[str, Any]:
    """Parse PDF/image/JSON into a structured dict with minimal heuristics."""
    p = Path(path)
    if p.suffix.lower() == ".json":
        return load_json_document(p)

    if p.suffix.lower() == ".pdf":
        pdf_bytes = p.read_bytes()
        doc_id = p.stem or uuid.uuid4().hex
        doc = _blank_w2(doc_id)

        form_fields = extract_acroform_fields(pdf_bytes)
        if form_fields:
            logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
            mapped = map_w2_fields_from_form(form_fields)
            _merge_form_mapping(doc, mapped)

        text, used_ocr = extract_text_from_pdf(p)
        text_doc = parse_w2_from_text(doc_id, text, used_ocr)
        doc = _merge_docs(doc, text_doc)
        doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
        if used_ocr:
            logger.info("Primary PDF extraction for %s relied on OCR fallback", doc_id)

        if _wages_missing(doc) and not used_ocr:
            logger.info("OCR fallback triggered for %s due to missing wage/tax fields", doc_id)
            ocr_text = _force_pdf_ocr(p)
            if ocr_text:
                ocr_doc = parse_w2_from_text(doc_id, ocr_text, used_ocr=True)
                doc = _merge_docs(doc, ocr_doc)
                doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), ocr_doc.get("ocr_quality", 1.0))

        if _wages_missing(doc):
            logger.warning("W-2 extraction incomplete for %s; key wage/tax fields still missing", doc_id)
        _log_missing_fields(doc)
        doc["meta"] = {"source_file": p.name}
        return doc

    if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}:
        text = extract_text_from_image(p)
        doc_id = p.stem or uuid.uuid4().hex
        doc = parse_w2_from_text(doc_id, text, used_ocr=True)
        _log_missing_fields(doc)
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
        doc_id = Path(filename).stem or uuid.uuid4().hex
        doc = _blank_w2(doc_id)
        form_fields = extract_acroform_fields(data)
        if form_fields:
            logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
            mapped = map_w2_fields_from_form(form_fields)
            _merge_form_mapping(doc, mapped)

        text, used_ocr = extract_text_from_pdf(BytesIO(data))
        text_doc = parse_w2_from_text(doc_id, text, used_ocr)
        doc = _merge_docs(doc, text_doc)
        doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
        if used_ocr:
            logger.info("Primary PDF extraction for %s relied on OCR fallback", doc_id)

        if _wages_missing(doc) and not used_ocr:
            logger.info("OCR fallback triggered for %s due to missing wage/tax fields", doc_id)
            ocr_text = _force_pdf_ocr(BytesIO(data))
            if ocr_text:
                ocr_doc = parse_w2_from_text(doc_id, ocr_text, used_ocr=True)
                doc = _merge_docs(doc, ocr_doc)
                doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), ocr_doc.get("ocr_quality", 1.0))

        if _wages_missing(doc):
            logger.warning("W-2 extraction incomplete for %s; key wage/tax fields still missing", doc_id)
        _log_missing_fields(doc)
        doc["meta"] = {"source_file": filename}
        return doc

    if suffix in {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}:
        text = extract_text_from_image_bytes(data)
        doc_id = Path(filename).stem or uuid.uuid4().hex
        doc = parse_w2_from_text(doc_id, text, used_ocr=True)
        _log_missing_fields(doc)
        doc["meta"] = {"source_file": filename}
        return doc

    raise ValueError(f"Unsupported file type: {suffix or 'unknown'}")
