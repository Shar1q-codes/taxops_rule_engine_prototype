"""Lightweight schema for normalized 1099-C documents."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


@dataclass
class Form1099C:
    doc_type: str = "1099-C"
    tax_year: Optional[int] = None

    creditor_name: str = ""
    creditor_tin: str = ""
    creditor_address: str = ""

    debtor_name: str = ""
    debtor_tin: str = ""
    debtor_address: str = ""

    account_number: Optional[str] = None

    box1_date_of_identifiable_event: Optional[str] = None
    box2_amount_of_debt_discharged: float = 0.0
    box3_interest_if_included: float = 0.0
    box4_debt_description: Optional[str] = None
    box5_debtor_personally_liable: bool = False
    box6_identifiable_event_code: Optional[str] = None
    box7_fair_market_value_property: float = 0.0

    state_tax_withheld: List[float] = field(default_factory=list)
    state_id: List[str] = field(default_factory=list)
    state_income: List[float] = field(default_factory=list)

    ocr_quality: Optional[float] = None
    source_pdf_path: str = ""
    extraction_engine_version: str = ""

    def to_document_dict(self) -> Dict[str, Any]:
        amounts = {
            "box2_amount_of_debt_discharged": _as_float(self.box2_amount_of_debt_discharged, 0.0),
            "box3_interest_if_included": _as_float(self.box3_interest_if_included, 0.0),
            "box7_fair_market_value_property": _as_float(self.box7_fair_market_value_property, 0.0),
            "federal_withholding": 0.0,
        }
        return {
            "doc_type": self.doc_type,
            "tax_year": self.tax_year,
            "creditor": {
                "name": self.creditor_name,
                "tin": self.creditor_tin,
                "address": self.creditor_address,
            },
            "debtor": {
                "name": self.debtor_name,
                "tin": self.debtor_tin,
                "address": self.debtor_address,
            },
            "account_number": self.account_number,
            "amounts": amounts,
            "box1_date_of_identifiable_event": self.box1_date_of_identifiable_event,
            "box4_debt_description": self.box4_debt_description,
            "box5_debtor_personally_liable": bool(self.box5_debtor_personally_liable),
            "box6_identifiable_event_code": self.box6_identifiable_event_code or "",
            "state_tax_withheld": [_as_float(v, 0.0) for v in self.state_tax_withheld],
            "state_id": list(self.state_id),
            "state_income": [_as_float(v, 0.0) for v in self.state_income],
            "ocr_quality": self.ocr_quality,
            "meta": {
                "source_pdf_path": self.source_pdf_path,
                "extraction_engine_version": self.extraction_engine_version,
            },
        }
