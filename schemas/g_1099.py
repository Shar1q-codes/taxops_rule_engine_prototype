"""Lightweight schema for normalized 1099-G documents."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


@dataclass
class Form1099G:
    doc_type: str = "1099-G"
    tax_year: Optional[int] = None

    payer_name: str = ""
    payer_tin: str = ""
    payer_address: str = ""

    recipient_name: str = ""
    recipient_tin: str = ""
    recipient_address: str = ""

    account_number: Optional[str] = None

    box1_unemployment_compensation: float = 0.0
    box2_state_local_tax_refunds: float = 0.0
    box3_box2_tax_year: Optional[int] = None
    box4_federal_income_tax_withheld: float = 0.0
    box5_rtaa_payments: float = 0.0
    box6_taxable_grants: float = 0.0
    box7_agricultural_payments: float = 0.0
    box8_trade_or_business_indicator: bool = False
    box9_market_gain: float = 0.0

    box10_state_tax_withheld: List[float] = field(default_factory=list)
    box11_state_id: List[str] = field(default_factory=list)
    box12_state_income: List[float] = field(default_factory=list)

    ocr_quality: Optional[float] = None
    source_pdf_path: str = ""
    extraction_engine_version: str = ""

    def to_document_dict(self) -> Dict[str, Any]:
        amounts = {
            "box1_unemployment_compensation": _as_float(self.box1_unemployment_compensation, 0.0),
            "box2_state_local_tax_refunds": _as_float(self.box2_state_local_tax_refunds, 0.0),
            "box4_federal_income_tax_withheld": _as_float(self.box4_federal_income_tax_withheld, 0.0),
            "box5_rtaa_payments": _as_float(self.box5_rtaa_payments, 0.0),
            "box6_taxable_grants": _as_float(self.box6_taxable_grants, 0.0),
            "box7_agricultural_payments": _as_float(self.box7_agricultural_payments, 0.0),
            "box9_market_gain": _as_float(self.box9_market_gain, 0.0),
            "federal_withholding": _as_float(self.box4_federal_income_tax_withheld, 0.0),
        }
        return {
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
            "account_number": self.account_number,
            "amounts": amounts,
            "box3_box2_tax_year": self.box3_box2_tax_year,
            "box8_trade_or_business_indicator": bool(self.box8_trade_or_business_indicator),
            "box10_state_tax_withheld": [_as_float(v, 0.0) for v in self.box10_state_tax_withheld],
            "box11_state_id": list(self.box11_state_id),
            "box12_state_income": [_as_float(v, 0.0) for v in self.box12_state_income],
            "ocr_quality": self.ocr_quality,
            "meta": {
                "source_pdf_path": self.source_pdf_path,
                "extraction_engine_version": self.extraction_engine_version,
            },
        }
