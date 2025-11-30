"""Lightweight schema for normalized 1099-K documents."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _normalize_months(values: Any) -> List[float]:
    if not isinstance(values, list):
        return [0.0] * 12
    normalized: List[float] = []
    for val in values[:12]:
        normalized.append(_as_float(val, 0.0))
    while len(normalized) < 12:
        normalized.append(0.0)
    return normalized


@dataclass
class StateItem:
    state_code: str = ""
    state_tax_withheld: float = 0.0

    def normalize(self) -> Dict[str, Any]:
        data = asdict(self)
        data["state_tax_withheld"] = _as_float(self.state_tax_withheld, 0.0)
        return data


@dataclass
class K1099Document:
    doc_type: str = "1099-K"
    tax_year: Optional[int] = None

    payer_name: str = ""
    payer_tin: str = ""
    payer_address: str = ""

    payee_name: str = ""
    payee_tin: str = ""
    payee_address: str = ""

    account_number: str = ""

    box_1a_gross_amount: float = 0.0
    box_1b_card_not_present: float = 0.0
    box_2_merchant_category_code: str = ""
    box_3_number_of_payment_transactions: float = 0.0
    box_4_federal_income_tax_withheld: float = 0.0
    monthly_totals: List[float] = field(default_factory=list)

    state_items: List[StateItem] = field(default_factory=list)

    ocr_quality: Optional[float] = None
    source_pdf_path: str = ""
    extraction_engine_version: str = ""

    def to_document_dict(self) -> Dict[str, Any]:
        months = _normalize_months(self.monthly_totals)
        amounts = {
            "box_1a_gross_amount": _as_float(self.box_1a_gross_amount, 0.0),
            "box_1b_card_not_present": _as_float(self.box_1b_card_not_present, 0.0),
            "box_3_number_of_payment_transactions": _as_float(self.box_3_number_of_payment_transactions, 0.0),
            "box_4_federal_income_tax_withheld": _as_float(self.box_4_federal_income_tax_withheld, 0.0),
            "monthly_totals": months,
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
                "name": self.payee_name,
                "tin": self.payee_tin,
                "address": self.payee_address,
            },
            "account_number": self.account_number,
            "amounts": amounts,
            "box_2_merchant_category_code": self.box_2_merchant_category_code,
            "state_items": [item.normalize() for item in self.state_items],
            "ocr_quality": self.ocr_quality,
            "meta": {
                "source_pdf_path": self.source_pdf_path,
                "extraction_engine_version": self.extraction_engine_version,
            },
        }
        return doc
