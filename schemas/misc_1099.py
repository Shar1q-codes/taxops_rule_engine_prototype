"""Lightweight schema for normalized 1099-MISC documents."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


@dataclass
class StateItem:
    state_code: str = ""
    state_id_number: str = ""
    state_tax_withheld: float = 0.0
    state_income: float = 0.0

    def normalize(self) -> Dict[str, Any]:
        data = asdict(self)
        data["state_tax_withheld"] = _as_float(self.state_tax_withheld, 0.0)
        data["state_income"] = _as_float(self.state_income, 0.0)
        return data


@dataclass
class Misc1099Document:
    doc_type: str = "1099-MISC"
    tax_year: Optional[int] = None

    payer_name: str = ""
    payer_tin: str = ""
    payer_address: str = ""

    recipient_name: str = ""
    recipient_tin: str = ""
    recipient_address: str = ""

    box_1_rents: float = 0.0
    box_2_royalties: float = 0.0
    box_3_other_income: float = 0.0
    box_4_federal_income_tax_withheld: float = 0.0
    box_6_medical_healthcare_payments: float = 0.0
    box_7_nonemployee_comp: float = 0.0  # older box 7 if present
    box_10_gross_proceeds_paid_to_attorney: float = 0.0

    state_items: List[StateItem] = field(default_factory=list)

    ocr_quality: Optional[float] = None
    source_pdf_path: str = ""
    extraction_engine_version: str = ""

    def to_document_dict(self) -> Dict[str, Any]:
        amounts = {
            "box_1_rents": _as_float(self.box_1_rents, 0.0),
            "box_2_royalties": _as_float(self.box_2_royalties, 0.0),
            "box_3_other_income": _as_float(self.box_3_other_income, 0.0),
            "box_4_federal_income_tax_withheld": _as_float(self.box_4_federal_income_tax_withheld, 0.0),
            "box_6_medical_healthcare_payments": _as_float(self.box_6_medical_healthcare_payments, 0.0),
            "box_7_nonemployee_comp": _as_float(self.box_7_nonemployee_comp, 0.0),
            "box_10_gross_proceeds_paid_to_attorney": _as_float(self.box_10_gross_proceeds_paid_to_attorney, 0.0),
            "federal_withholding": _as_float(self.box_4_federal_income_tax_withheld, 0.0),
        }
        doc: Dict[str, Any] = {
            "doc_type": self.doc_type,
            "tax_year": self.tax_year,
            "payer": {
                "name": self.payer_name,
                "tin": self.payer_tin,
                "address": self.payer_address,
            },
            "recipient": {
                "name": self.recipient_name,
                "tin": self.recipient_tin,
                "address": self.recipient_address,
            },
            "amounts": amounts,
            "state_items": [item.normalize() for item in self.state_items],
            "ocr_quality": self.ocr_quality,
            "meta": {
                "source_pdf_path": self.source_pdf_path,
                "extraction_engine_version": self.extraction_engine_version,
            },
        }
        return doc
