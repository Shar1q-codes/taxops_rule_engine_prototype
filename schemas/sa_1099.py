"""Lightweight schema for normalized 1099-SA documents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


@dataclass
class Form1099SA:
    doc_type: str = "1099-SA"
    tax_year: Optional[int] = None

    payer_name: str = ""
    payer_tin: str = ""
    payer_address: str = ""

    recipient_name: str = ""
    recipient_tin: str = ""
    recipient_address: str = ""

    account_number: Optional[str] = None

    box1_gross_distribution: float = 0.0
    box2_earnings_on_excess_contributions: float = 0.0
    box3_distribution_code: str = ""
    box4_federal_income_tax_withheld: float = 0.0
    box5_fair_market_value_hsa_msa: float = 0.0

    hsa: bool = False
    archer_msa: bool = False
    ma_msa: bool = False

    state_tax_withheld: List[float] = field(default_factory=list)
    state_id: List[str] = field(default_factory=list)
    state_income: List[float] = field(default_factory=list)

    ocr_quality: Optional[float] = None
    source_pdf_path: str = ""
    extraction_engine_version: str = ""

    def to_document_dict(self) -> Dict[str, Any]:
        amounts = {
            "box1_gross_distribution": _as_float(self.box1_gross_distribution, 0.0),
            "box2_earnings_on_excess_contributions": _as_float(self.box2_earnings_on_excess_contributions, 0.0),
            "box4_federal_income_tax_withheld": _as_float(self.box4_federal_income_tax_withheld, 0.0),
            "box5_fair_market_value_hsa_msa": _as_float(self.box5_fair_market_value_hsa_msa, 0.0),
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
            "box3_distribution_code": self.box3_distribution_code,
            "hsa": bool(self.hsa),
            "archer_msa": bool(self.archer_msa),
            "ma_msa": bool(self.ma_msa),
            "state_tax_withheld": [_as_float(v, 0.0) for v in self.state_tax_withheld],
            "state_id": list(self.state_id),
            "state_income": [_as_float(v, 0.0) for v in self.state_income],
            "ocr_quality": self.ocr_quality,
            "meta": {
                "source_pdf_path": self.source_pdf_path,
                "extraction_engine_version": self.extraction_engine_version,
            },
        }
