"""Lightweight schema for normalized 1099-DIV documents."""

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

    def normalize(self) -> Dict[str, Any]:
        data = asdict(self)
        data["state_tax_withheld"] = _as_float(self.state_tax_withheld, 0.0)
        return data


@dataclass
class Div1099Document:
    doc_type: str = "1099-DIV"
    tax_year: Optional[int] = None

    payer_name: str = ""
    payer_tin: str = ""
    payer_address: str = ""

    recipient_name: str = ""
    recipient_tin: str = ""
    recipient_address: str = ""

    box_1a_total_ordinary_dividends: float = 0.0
    box_1b_qualified_dividends: float = 0.0
    box_2a_total_capital_gain_distributions: float = 0.0
    box_4_federal_income_tax_withheld: float = 0.0
    box_6_foreign_tax_paid: float = 0.0
    box_7_foreign_country_or_possession: str = ""
    box_11_section_199a_dividends: float = 0.0
    box_12_exempt_interest_dividends: float = 0.0
    box_13_specified_private_activity_bond_interest_dividends: float = 0.0

    state_items: List[StateItem] = field(default_factory=list)

    ocr_quality: Optional[float] = None
    source_pdf_path: str = ""
    extraction_engine_version: str = ""

    def to_document_dict(self) -> Dict[str, Any]:
        amounts = {
            "box_1a_total_ordinary_dividends": _as_float(self.box_1a_total_ordinary_dividends, 0.0),
            "box_1b_qualified_dividends": _as_float(self.box_1b_qualified_dividends, 0.0),
            "box_2a_total_capital_gain_distributions": _as_float(self.box_2a_total_capital_gain_distributions, 0.0),
            "box_4_federal_income_tax_withheld": _as_float(self.box_4_federal_income_tax_withheld, 0.0),
            "box_6_foreign_tax_paid": _as_float(self.box_6_foreign_tax_paid, 0.0),
            "box_11_section_199a_dividends": _as_float(self.box_11_section_199a_dividends, 0.0),
            "box_12_exempt_interest_dividends": _as_float(self.box_12_exempt_interest_dividends, 0.0),
            "box_13_specified_private_activity_bond_interest_dividends": _as_float(
                self.box_13_specified_private_activity_bond_interest_dividends, 0.0
            ),
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
            "box_7_foreign_country_or_possession": self.box_7_foreign_country_or_possession,
            "ocr_quality": self.ocr_quality,
            "meta": {
                "source_pdf_path": self.source_pdf_path,
                "extraction_engine_version": self.extraction_engine_version,
            },
        }
        return doc
