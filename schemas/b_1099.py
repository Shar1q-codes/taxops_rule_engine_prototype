"""Lightweight schema for normalized 1099-B documents (broker/barter transactions)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


@dataclass
class Transaction:
    description_of_property: str = ""
    date_acquired: str = ""
    date_sold: str = ""
    proceeds_gross: float = 0.0
    cost_or_other_basis: float = 0.0
    accrued_market_discount: float = 0.0
    wash_sale_disallowed: float = 0.0
    federal_income_tax_withheld: float = 0.0
    type_of_gain_loss_code: str = ""
    basis_reported_to_irs_flag: bool = False
    noncovered_security_flag: bool = False
    bartering_flag: bool = False
    adjustments_code: str = ""
    adjustments_amount: float = 0.0

    def normalize(self) -> Dict[str, Any]:
        return {
            "description_of_property": self.description_of_property,
            "date_acquired": self.date_acquired,
            "date_sold": self.date_sold,
            "proceeds_gross": _as_float(self.proceeds_gross, 0.0),
            "cost_or_other_basis": _as_float(self.cost_or_other_basis, 0.0),
            "accrued_market_discount": _as_float(self.accrued_market_discount, 0.0),
            "wash_sale_disallowed": _as_float(self.wash_sale_disallowed, 0.0),
            "federal_income_tax_withheld": _as_float(self.federal_income_tax_withheld, 0.0),
            "type_of_gain_loss_code": self.type_of_gain_loss_code,
            "basis_reported_to_irs_flag": bool(self.basis_reported_to_irs_flag),
            "noncovered_security_flag": bool(self.noncovered_security_flag),
            "bartering_flag": bool(self.bartering_flag),
            "adjustments_code": self.adjustments_code,
            "adjustments_amount": _as_float(self.adjustments_amount, 0.0),
        }


@dataclass
class B1099Document:
    doc_type: str = "1099-B"
    tax_year: Optional[int] = None

    broker_name: str = ""
    broker_tin: str = ""
    broker_address: str = ""

    recipient_name: str = ""
    recipient_tin: str = ""
    recipient_address: str = ""

    transactions: List[Transaction] = field(default_factory=list)

    ocr_quality: Optional[float] = None
    source_pdf_path: str = ""
    extraction_engine_version: str = ""

    def to_document_dict(self) -> Dict[str, Any]:
        return {
            "doc_type": self.doc_type,
            "tax_year": self.tax_year,
            "broker": {
                "name": self.broker_name,
                "tin": self.broker_tin,
                "address": self.broker_address,
            },
            "recipient": {
                "name": self.recipient_name,
                "tin": self.recipient_tin,
                "address": self.recipient_address,
            },
            "transactions": [t.normalize() for t in self.transactions],
            "ocr_quality": self.ocr_quality,
            "meta": {
                "source_pdf_path": self.source_pdf_path,
                "extraction_engine_version": self.extraction_engine_version,
            },
        }
