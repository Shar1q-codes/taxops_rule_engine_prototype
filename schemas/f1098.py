"""Lightweight schema for normalized Form 1098 (Mortgage Interest Statement)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


@dataclass
class F1098Document:
    doc_type: str = "1098"
    tax_year: Optional[int] = None

    lender_name: str = ""
    lender_tin: str = ""
    lender_address: str = ""

    borrower_name: str = ""
    borrower_tin: str = ""
    borrower_address: str = ""

    box_1_mortgage_interest_received: float = 0.0
    box_2_outstanding_mortgage_principal: float = 0.0
    box_3_mortgage_origination_date: str = ""
    box_4_refunded_interest: float = 0.0
    box_5_mortgage_insurance_premiums: float = 0.0
    box_6_points_paid_on_purchase: float = 0.0
    box_7_mortgaged_property_address: str = ""
    box_8_mortgaged_property_account_number: str = ""
    box_9_additional_mortgaged_property_info: str = ""

    ocr_quality: Optional[float] = None
    source_pdf_path: str = ""
    extraction_engine_version: str = ""

    def to_document_dict(self) -> Dict[str, Any]:
        amounts = {
            "box_1_mortgage_interest_received": _as_float(self.box_1_mortgage_interest_received, 0.0),
            "box_2_outstanding_mortgage_principal": _as_float(self.box_2_outstanding_mortgage_principal, 0.0),
            "box_4_refunded_interest": _as_float(self.box_4_refunded_interest, 0.0),
            "box_5_mortgage_insurance_premiums": _as_float(self.box_5_mortgage_insurance_premiums, 0.0),
            "box_6_points_paid_on_purchase": _as_float(self.box_6_points_paid_on_purchase, 0.0),
        }
        doc: Dict[str, Any] = {
            "doc_type": self.doc_type,
            "tax_year": self.tax_year,
            "payer": {
                "name": self.lender_name,
                "tin": self.lender_tin,
                "address": self.lender_address,
            },
            "recipient": {
                "name": self.borrower_name,
                "tin": self.borrower_tin,
                "address": self.borrower_address,
            },
            "amounts": amounts,
            "box_3_mortgage_origination_date": self.box_3_mortgage_origination_date,
            "box_7_mortgaged_property_address": self.box_7_mortgaged_property_address,
            "box_8_mortgaged_property_account_number": self.box_8_mortgaged_property_account_number,
            "box_9_additional_mortgaged_property_info": self.box_9_additional_mortgaged_property_info,
            "ocr_quality": self.ocr_quality,
            "meta": {
                "source_pdf_path": self.source_pdf_path,
                "extraction_engine_version": self.extraction_engine_version,
            },
        }
        return doc
