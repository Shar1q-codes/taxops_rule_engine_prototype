"""Lightweight schema for normalized 1099-R documents (standard mode)."""

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
    state_distribution_amount: float = 0.0

    def normalize(self) -> Dict[str, Any]:
        data = asdict(self)
        data["state_tax_withheld"] = _as_float(self.state_tax_withheld, 0.0)
        data["state_distribution_amount"] = _as_float(self.state_distribution_amount, 0.0)
        return data


@dataclass
class R1099Document:
    doc_type: str = "1099-R"
    tax_year: Optional[int] = None

    payer_name: str = ""
    payer_tin: str = ""
    payer_address: str = ""

    recipient_name: str = ""
    recipient_tin: str = ""
    recipient_address: str = ""

    account_number: str = ""

    box_1_gross_distribution: float = 0.0
    box_2a_taxable_amount: float = 0.0
    box_2b_taxable_amount_not_determined: bool = False
    box_2b_total_distribution: bool = False
    box_3_capital_gain_included: float = 0.0
    box_4_federal_income_tax_withheld: float = 0.0
    box_5_employee_contributions_or_insurance_premiums: float = 0.0
    box_6_net_unrealized_appreciation: float = 0.0
    box_7_distribution_codes: List[str] = field(default_factory=list)
    box_7_ira_sep_simple_indicator: bool = False
    box_8_other: float = 0.0
    box_9a_total_distribution_pct: float = 0.0
    box_9b_total_employee_contributions: float = 0.0
    box_10_amount_allocable_to_IRR: float = 0.0
    box_11_first_year_designated_roth: Optional[int] = None
    box_12_fatca_filing_requirement: bool = False
    box_13_date_of_payment: str = ""
    box_14_state_tax_withheld: List[float] = field(default_factory=list)
    box_15_state_id: List[str] = field(default_factory=list)
    box_16_state_distribution: List[float] = field(default_factory=list)

    state_items: List[StateItem] = field(default_factory=list)

    ocr_quality: Optional[float] = None
    source_pdf_path: str = ""
    extraction_engine_version: str = ""

    def to_document_dict(self) -> Dict[str, Any]:
        amounts = {
            "box_1_gross_distribution": _as_float(self.box_1_gross_distribution, 0.0),
            "box_2a_taxable_amount": _as_float(self.box_2a_taxable_amount, 0.0),
            "box_3_capital_gain_included": _as_float(self.box_3_capital_gain_included, 0.0),
            "box_4_federal_income_tax_withheld": _as_float(self.box_4_federal_income_tax_withheld, 0.0),
            "box_5_employee_contributions_or_insurance_premiums": _as_float(
                self.box_5_employee_contributions_or_insurance_premiums, 0.0
            ),
            "box_6_net_unrealized_appreciation": _as_float(self.box_6_net_unrealized_appreciation, 0.0),
            "box_8_other": _as_float(self.box_8_other, 0.0),
            "box_9a_total_distribution_pct": _as_float(self.box_9a_total_distribution_pct, 0.0),
            "box_9b_total_employee_contributions": _as_float(self.box_9b_total_employee_contributions, 0.0),
            "box_10_amount_allocable_to_IRR": _as_float(self.box_10_amount_allocable_to_IRR, 0.0),
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
            "account_number": self.account_number,
            "amounts": amounts,
            "box_2b_taxable_amount_not_determined": bool(self.box_2b_taxable_amount_not_determined),
            "box_2b_total_distribution": bool(self.box_2b_total_distribution),
            "box_7_distribution_code": " ".join(self.box_7_distribution_codes) if self.box_7_distribution_codes else "",
            "box_7_distribution_codes": list(self.box_7_distribution_codes),
            "box_7_ira_sep_simple_indicator": bool(self.box_7_ira_sep_simple_indicator),
            "box_11_first_year_designated_roth": self.box_11_first_year_designated_roth,
            "box_12_fatca_filing_requirement": bool(self.box_12_fatca_filing_requirement),
            "box_13_date_of_payment": self.box_13_date_of_payment,
            "box_14_state_tax_withheld": [ _as_float(v, 0.0) for v in self.box_14_state_tax_withheld ],
            "box_15_state_id": list(self.box_15_state_id),
            "box_16_state_distribution": [ _as_float(v, 0.0) for v in self.box_16_state_distribution ],
            "state_items": [item.normalize() for item in self.state_items],
            "ocr_quality": self.ocr_quality,
            "meta": {
                "source_pdf_path": self.source_pdf_path,
                "extraction_engine_version": self.extraction_engine_version,
            },
        }
        return doc
