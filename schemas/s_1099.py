"""Lightweight schema for normalized 1099-S documents."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


@dataclass
class Form1099S:
    doc_type: str = "1099-S"
    tax_year: Optional[int] = None

    filer_name: str = ""
    filer_tin: str = ""
    filer_address: str = ""

    transferor_name: str = ""
    transferor_tin: str = ""
    transferor_address: str = ""

    account_number: Optional[str] = None
    property_address: Optional[str] = None
    property_desc: Optional[str] = None

    box1_gross_proceeds: float = 0.0
    box2_property_or_services: bool = False
    box3_recipient_is_transferor: bool = False
    box4_federal_income_tax_withheld: float = 0.0
    box5_transferor_is_foreign: bool = False

    closing_date: Optional[str] = None

    state_tax_withheld: List[float] = field(default_factory=list)
    state_id: List[str] = field(default_factory=list)
    state_income: List[float] = field(default_factory=list)

    ocr_quality: Optional[float] = None
    source_pdf_path: str = ""
    extraction_engine_version: str = ""

    def to_document_dict(self) -> Dict[str, Any]:
        amounts = {
            "box1_gross_proceeds": _as_float(self.box1_gross_proceeds, 0.0),
            "box4_federal_income_tax_withheld": _as_float(self.box4_federal_income_tax_withheld, 0.0),
            "federal_withholding": _as_float(self.box4_federal_income_tax_withheld, 0.0),
        }
        return {
            "doc_type": self.doc_type,
            "tax_year": self.tax_year,
            "filer": {
                "name": self.filer_name,
                "tin": self.filer_tin,
                "address": self.filer_address,
            },
            "transferor": {
                "name": self.transferor_name,
                "tin": self.transferor_tin,
                "address": self.transferor_address,
            },
            "account_number": self.account_number,
            "property_address": self.property_address,
            "property_desc": self.property_desc,
            "closing_date": self.closing_date,
            "amounts": amounts,
            "box2_property_or_services": bool(self.box2_property_or_services),
            "box3_recipient_is_transferor": bool(self.box3_recipient_is_transferor),
            "box5_transferor_is_foreign": bool(self.box5_transferor_is_foreign),
            "state_tax_withheld": [_as_float(v, 0.0) for v in self.state_tax_withheld],
            "state_id": list(self.state_id),
            "state_income": [_as_float(v, 0.0) for v in self.state_income],
            "ocr_quality": self.ocr_quality,
            "meta": {
                "source_pdf_path": self.source_pdf_path,
                "extraction_engine_version": self.extraction_engine_version,
            },
        }
