"""Lightweight schema for normalized Form 1095-A (Health Insurance Marketplace Statement)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


@dataclass
class CoveredIndividual:
    name: str = ""
    ssn_or_tin: str = ""
    coverage_start: str = ""
    coverage_end: str = ""

    def normalize(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MonthEntry:
    month_index: int = 0
    monthly_premium: float = 0.0
    slcsp_premium: float = 0.0
    advance_premium_tax_credit: float = 0.0

    def normalize(self) -> Dict[str, Any]:
        return {
            "month_index": self.month_index,
            "monthly_premium": _as_float(self.monthly_premium, 0.0),
            "slcsp_premium": _as_float(self.slcsp_premium, 0.0),
            "advance_premium_tax_credit": _as_float(self.advance_premium_tax_credit, 0.0),
        }


@dataclass
class F1095ADocument:
    doc_type: str = "1095-A"
    tax_year: Optional[int] = None

    issuer_name: str = ""
    issuer_ein: str = ""
    issuer_address: str = ""

    recipient_name: str = ""
    recipient_ssn_or_tin: str = ""
    recipient_address: str = ""

    covered_individuals: List[CoveredIndividual] = field(default_factory=list)
    months: List[MonthEntry] = field(default_factory=list)

    ocr_quality: Optional[float] = None
    source_pdf_path: str = ""
    extraction_engine_version: str = ""

    def to_document_dict(self) -> Dict[str, Any]:
        doc: Dict[str, Any] = {
            "doc_type": self.doc_type,
            "tax_year": self.tax_year,
            "issuer": {
                "name": self.issuer_name,
                "ein": self.issuer_ein,
                "address": self.issuer_address,
            },
            "recipient": {
                "name": self.recipient_name,
                "tin": self.recipient_ssn_or_tin,
                "address": self.recipient_address,
            },
            "covered_individuals": [ci.normalize() for ci in self.covered_individuals],
            "months": [m.normalize() for m in self.months],
            "ocr_quality": self.ocr_quality,
            "meta": {
                "source_pdf_path": self.source_pdf_path,
                "extraction_engine_version": self.extraction_engine_version,
            },
        }
        return doc
