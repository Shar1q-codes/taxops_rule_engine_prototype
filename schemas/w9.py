"""Lightweight schema for normalized Form W-9 (Request for TIN and Certification)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


@dataclass
class W9Document:
    doc_type: str = "W-9"
    tax_year: Optional[int] = None
    requestor_name: str = ""

    taxpayer_name: str = ""
    business_name_disregarded: str = ""
    federal_tax_classification: str = ""
    llc_tax_class_code: str = ""
    exempt_payee_code: str = ""
    fatca_exemption_code: str = ""

    address_line1: str = ""
    address_line2: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""

    ssn: str = ""
    ein: str = ""
    tin_raw: str = ""

    certification_signed_flag: bool = False
    certification_date: str = ""

    ocr_quality: Optional[float] = None
    source_pdf_path: str = ""
    extraction_engine_version: str = ""

    def to_document_dict(self) -> Dict[str, Any]:
        return {
            "doc_type": self.doc_type,
            "tax_year": self.tax_year,
            "requestor_name": self.requestor_name,
            "taxpayer_name": self.taxpayer_name,
            "business_name_disregarded": self.business_name_disregarded,
            "federal_tax_classification": self.federal_tax_classification,
            "llc_tax_class_code": self.llc_tax_class_code,
            "exempt_payee_code": self.exempt_payee_code,
            "fatca_exemption_code": self.fatca_exemption_code,
            "address_line1": self.address_line1,
            "address_line2": self.address_line2,
            "city": self.city,
            "state": self.state,
            "zip_code": self.zip_code,
            "ssn": self.ssn,
            "ein": self.ein,
            "tin_raw": self.tin_raw,
            "certification_signed_flag": self.certification_signed_flag,
            "certification_date": self.certification_date,
            "ocr_quality": self.ocr_quality,
            "meta": {
                "source_pdf_path": self.source_pdf_path,
                "extraction_engine_version": self.extraction_engine_version,
            },
        }
