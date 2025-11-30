"""Lightweight schema for normalized Form 941 (Employer's Quarterly Federal Tax Return)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


@dataclass
class F941Document:
    doc_type: str = "941"
    tax_year: Optional[int] = None
    tax_quarter: Optional[int] = None

    employer_name: str = ""
    employer_ein: str = ""
    employer_address: str = ""

    line_1_num_employees: float = 0.0
    line_2_wages_tips_other_comp: float = 0.0
    line_3_income_tax_withheld: float = 0.0

    line_5a_taxable_ss_wages: float = 0.0
    line_5a_ss_tax: float = 0.0
    line_5b_taxable_ss_tips: float = 0.0
    line_5b_ss_tax_tips: float = 0.0
    line_5c_taxable_medicare_wages: float = 0.0
    line_5c_medicare_tax: float = 0.0
    line_5d_taxable_addl_medicare_wages: float = 0.0
    line_5d_addl_medicare_tax: float = 0.0

    line_6_total_taxes_before_adjustments: float = 0.0
    line_7_current_quarter_fractions_of_cents_adjustment: float = 0.0
    line_8_tip_adjustment: float = 0.0
    line_9_sick_pay_adjustment: float = 0.0
    line_10_total_taxes_after_adjustments: float = 0.0
    line_11_total_deposits_for_quarter: float = 0.0
    line_12_refundable_credits: float = 0.0
    line_13_total_taxes_after_credits: float = 0.0
    line_14_balance_due: float = 0.0
    line_15_overpayment: float = 0.0

    ocr_quality: Optional[float] = None
    source_pdf_path: str = ""
    extraction_engine_version: str = ""

    def to_document_dict(self) -> Dict[str, Any]:
        amounts: Dict[str, Any] = {
            "line_1_num_employees": _as_float(self.line_1_num_employees, 0.0),
            "line_2_wages_tips_other_comp": _as_float(self.line_2_wages_tips_other_comp, 0.0),
            "line_3_income_tax_withheld": _as_float(self.line_3_income_tax_withheld, 0.0),
            "line_5a_taxable_ss_wages": _as_float(self.line_5a_taxable_ss_wages, 0.0),
            "line_5a_ss_tax": _as_float(self.line_5a_ss_tax, 0.0),
            "line_5b_taxable_ss_tips": _as_float(self.line_5b_taxable_ss_tips, 0.0),
            "line_5b_ss_tax_tips": _as_float(self.line_5b_ss_tax_tips, 0.0),
            "line_5c_taxable_medicare_wages": _as_float(self.line_5c_taxable_medicare_wages, 0.0),
            "line_5c_medicare_tax": _as_float(self.line_5c_medicare_tax, 0.0),
            "line_5d_taxable_addl_medicare_wages": _as_float(self.line_5d_taxable_addl_medicare_wages, 0.0),
            "line_5d_addl_medicare_tax": _as_float(self.line_5d_addl_medicare_tax, 0.0),
            "line_6_total_taxes_before_adjustments": _as_float(self.line_6_total_taxes_before_adjustments, 0.0),
            "line_7_current_quarter_fractions_of_cents_adjustment": _as_float(self.line_7_current_quarter_fractions_of_cents_adjustment, 0.0),
            "line_8_tip_adjustment": _as_float(self.line_8_tip_adjustment, 0.0),
            "line_9_sick_pay_adjustment": _as_float(self.line_9_sick_pay_adjustment, 0.0),
            "line_10_total_taxes_after_adjustments": _as_float(self.line_10_total_taxes_after_adjustments, 0.0),
            "line_11_total_deposits_for_quarter": _as_float(self.line_11_total_deposits_for_quarter, 0.0),
            "line_12_refundable_credits": _as_float(self.line_12_refundable_credits, 0.0),
            "line_13_total_taxes_after_credits": _as_float(self.line_13_total_taxes_after_credits, 0.0),
            "line_14_balance_due": _as_float(self.line_14_balance_due, 0.0),
            "line_15_overpayment": _as_float(self.line_15_overpayment, 0.0),
        }
        doc: Dict[str, Any] = {
            "doc_type": self.doc_type,
            "tax_year": self.tax_year,
            "tax_quarter": self.tax_quarter,
            "employer": {
                "name": self.employer_name,
                "ein": self.employer_ein,
                "address": self.employer_address,
            },
            "amounts": amounts,
            "ocr_quality": self.ocr_quality,
            "meta": {
                "source_pdf_path": self.source_pdf_path,
                "extraction_engine_version": self.extraction_engine_version,
            },
        }
        return doc
