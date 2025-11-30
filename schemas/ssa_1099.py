"""Lightweight schema for normalized SSA-1099 (Social Security Benefit Statement) documents."""

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
    state_tax_withheld: float = 0.0
    state_id_number: str = ""

    def normalize(self) -> Dict[str, Any]:
        data = asdict(self)
        data["state_tax_withheld"] = _as_float(self.state_tax_withheld, 0.0)
        return data


@dataclass
class SSA1099Document:
    doc_type: str = "SSA-1099"
    tax_year: Optional[int] = None

    payer_name: str = "Social Security Administration"
    payer_tin: str = ""
    payer_address: str = ""

    beneficiary_name: str = ""
    beneficiary_tin: str = ""
    beneficiary_address: str = ""

    box_3_benefits_paid: float = 0.0
    box_4_benefits_repaid: float = 0.0
    box_5_net_benefits: float = 0.0
    box_6_voluntary_federal_tax_withheld: float = 0.0
    box_7_medicare_premiums: float = 0.0
    box_8_other_deductions_or_adjustments: float = 0.0
    box_9_state_repayment: float = 0.0

    state_items: List[StateItem] = field(default_factory=list)

    ocr_quality: Optional[float] = None
    source_pdf_path: str = ""
    extraction_engine_version: str = ""

    def to_document_dict(self) -> Dict[str, Any]:
        amounts = {
            "box_3_benefits_paid": _as_float(self.box_3_benefits_paid, 0.0),
            "box_4_benefits_repaid": _as_float(self.box_4_benefits_repaid, 0.0),
            "box_5_net_benefits": _as_float(self.box_5_net_benefits, 0.0),
            "box_6_voluntary_federal_tax_withheld": _as_float(self.box_6_voluntary_federal_tax_withheld, 0.0),
            "box_7_medicare_premiums": _as_float(self.box_7_medicare_premiums, 0.0),
            "box_8_other_deductions_or_adjustments": _as_float(self.box_8_other_deductions_or_adjustments, 0.0),
            "box_9_state_repayment": _as_float(self.box_9_state_repayment, 0.0),
            "federal_withholding": _as_float(self.box_6_voluntary_federal_tax_withheld, 0.0),
        }
        return {
            "doc_type": self.doc_type,
            "tax_year": self.tax_year,
            "payer": {
                "name": self.payer_name,
                "tin": self.payer_tin,
                "address": self.payer_address,
            },
            "beneficiary": {
                "name": self.beneficiary_name,
                "tin": self.beneficiary_tin,
                "address": self.beneficiary_address,
            },
            "amounts": amounts,
            "state_items": [item.normalize() for item in self.state_items],
            "ocr_quality": self.ocr_quality,
            "meta": {
                "source_pdf_path": self.source_pdf_path,
                "extraction_engine_version": self.extraction_engine_version,
            },
        }
