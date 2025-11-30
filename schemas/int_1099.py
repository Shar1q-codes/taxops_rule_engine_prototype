"""Lightweight schema for normalized 1099-INT documents."""

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

    def normalize(self) -> Dict[str, Any]:
        data = asdict(self)
        data["state_tax_withheld"] = _as_float(self.state_tax_withheld, 0.0)
        return data


@dataclass
class Int1099Document:
    doc_type: str = "1099-INT"
    tax_year: Optional[int] = None

    payer_name: str = ""
    payer_tin: str = ""
    payer_address: str = ""

    recipient_name: str = ""
    recipient_tin: str = ""
    recipient_address: str = ""

    account_number: str = ""

    box_1_interest_income: float = 0.0
    box_2_early_withdrawal_penalty: float = 0.0
    box_3_us_savings_bonds_and_treasury_interest: float = 0.0
    box_4_federal_income_tax_withheld: float = 0.0
    box_5_investment_expenses: float = 0.0
    box_6_foreign_tax_paid: float = 0.0
    box_7_foreign_country_or_ust_possession: str = ""
    box_8_tax_exempt_interest: float = 0.0
    box_9_specified_private_activity_bond_interest: float = 0.0
    box_10_market_discount: float = 0.0
    box_11_bond_premium: float = 0.0
    box_12_bond_premium_tax_exempt: float = 0.0
    box_13_bond_premium_treasury: float = 0.0

    box_6_foreign_country: str = ""
    box_14_tax_exempt_cusip: str = ""

    box_15_state: List[str] = field(default_factory=list)
    box_16_state_tax_withheld: List[float] = field(default_factory=list)
    box_17_state_id: List[str] = field(default_factory=list)

    state_items: List[StateItem] = field(default_factory=list)

    ocr_quality: Optional[float] = None
    source_pdf_path: str = ""
    extraction_engine_version: str = ""

    def to_document_dict(self) -> Dict[str, Any]:
        """Map into the dict layout expected by the rule engine."""
        amounts = {
            "box_1_interest_income": _as_float(self.box_1_interest_income, 0.0),
            "box_2_early_withdrawal_penalty": _as_float(self.box_2_early_withdrawal_penalty, 0.0),
            "box_3_us_savings_bonds_and_treasury_interest": _as_float(
                self.box_3_us_savings_bonds_and_treasury_interest, 0.0
            ),
            "box_4_federal_income_tax_withheld": _as_float(self.box_4_federal_income_tax_withheld, 0.0),
            "box_5_investment_expenses": _as_float(self.box_5_investment_expenses, 0.0),
            "box_6_foreign_tax_paid": _as_float(self.box_6_foreign_tax_paid, 0.0),
            "box_8_tax_exempt_interest": _as_float(self.box_8_tax_exempt_interest, 0.0),
            "box_9_specified_private_activity_bond_interest": _as_float(
                self.box_9_specified_private_activity_bond_interest, 0.0
            ),
            "box_10_market_discount": _as_float(self.box_10_market_discount, 0.0),
            "box_11_bond_premium": _as_float(self.box_11_bond_premium, 0.0),
            "box_12_bond_premium_tax_exempt": _as_float(self.box_12_bond_premium_tax_exempt, 0.0),
            "box_13_bond_premium_treasury": _as_float(self.box_13_bond_premium_treasury, 0.0),
            # Aliases to align with generic fields where possible
            "federal_withholding": _as_float(self.box_4_federal_income_tax_withheld, 0.0),
            "state_withholding": 0.0,
            "interest_income": _as_float(self.box_1_interest_income, 0.0),
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
            "box_6_foreign_country_or_ust_possession": self.box_6_foreign_country,
            "box_14_tax_exempt_cusip": self.box_14_tax_exempt_cusip,
            "box_15_state": list(self.box_15_state),
            "box_16_state_tax_withheld": [_as_float(v, 0.0) for v in self.box_16_state_tax_withheld],
            "box_17_state_id": list(self.box_17_state_id),
            "amounts": amounts,
            "state_items": [item.normalize() for item in self.state_items],
            "ocr_quality": self.ocr_quality,
            "meta": {
                "source_pdf_path": self.source_pdf_path,
                "extraction_engine_version": self.extraction_engine_version,
            },
        }
        return doc
