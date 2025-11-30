"""Lightweight schema for normalized Form 5498 documents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


@dataclass
class Form5498:
    doc_type: str = "5498"
    tax_year: Optional[int] = None

    trustee_name: str = ""
    trustee_tin: str = ""
    trustee_address: str = ""

    participant_name: str = ""
    participant_tin: str = ""
    participant_address: str = ""

    account_number: Optional[str] = None

    traditional_ira: bool = False
    roth_ira: bool = False
    sep_ira: bool = False
    simple_ira: bool = False
    hsa: bool = False
    esa_cesa: bool = False

    box1_ira_contributions: float = 0.0
    box2_rollover_contributions: float = 0.0
    box3_roth_ira_conversion_amount: float = 0.0
    box4_recharacterized_contributions: float = 0.0
    box5_fmv_of_account: float = 0.0
    box6_life_insurance_cost_in_ira: float = 0.0
    box7_roth_ira_contributions: float = 0.0
    box8_sep_contributions: float = 0.0
    box9_simple_contributions: float = 0.0
    box10_roth_ira_fmv_rollovers: float = 0.0
    box11_required_minimum_distribution_indicator: bool = False
    box12_rmd_date: Optional[str] = None
    box13_rmd_amount: float = 0.0
    box14_hsa_msa_contributions: float = 0.0
    box15_other_contributions: float = 0.0

    ocr_quality: Optional[float] = None
    source_pdf_path: str = ""
    extraction_engine_version: str = ""

    def to_document_dict(self) -> Dict[str, Any]:
        amounts = {
            "box1_ira_contributions": _as_float(self.box1_ira_contributions, 0.0),
            "box2_rollover_contributions": _as_float(self.box2_rollover_contributions, 0.0),
            "box3_roth_ira_conversion_amount": _as_float(self.box3_roth_ira_conversion_amount, 0.0),
            "box4_recharacterized_contributions": _as_float(self.box4_recharacterized_contributions, 0.0),
            "box5_fmv_of_account": _as_float(self.box5_fmv_of_account, 0.0),
            "box6_life_insurance_cost_in_ira": _as_float(self.box6_life_insurance_cost_in_ira, 0.0),
            "box7_roth_ira_contributions": _as_float(self.box7_roth_ira_contributions, 0.0),
            "box8_sep_contributions": _as_float(self.box8_sep_contributions, 0.0),
            "box9_simple_contributions": _as_float(self.box9_simple_contributions, 0.0),
            "box10_roth_ira_fmv_rollovers": _as_float(self.box10_roth_ira_fmv_rollovers, 0.0),
            "box13_rmd_amount": _as_float(self.box13_rmd_amount, 0.0),
            "box14_hsa_msa_contributions": _as_float(self.box14_hsa_msa_contributions, 0.0),
            "box15_other_contributions": _as_float(self.box15_other_contributions, 0.0),
        }
        return {
            "doc_type": self.doc_type,
            "tax_year": self.tax_year,
            "trustee": {
                "name": self.trustee_name,
                "tin": self.trustee_tin,
                "address": self.trustee_address,
            },
            "participant": {
                "name": self.participant_name,
                "tin": self.participant_tin,
                "address": self.participant_address,
            },
            "account_number": self.account_number,
            "amounts": amounts,
            "box11_required_minimum_distribution_indicator": bool(self.box11_required_minimum_distribution_indicator),
            "box12_rmd_date": self.box12_rmd_date,
            "flags": {
                "traditional_ira": bool(self.traditional_ira),
                "roth_ira": bool(self.roth_ira),
                "sep_ira": bool(self.sep_ira),
                "simple_ira": bool(self.simple_ira),
                "hsa": bool(self.hsa),
                "esa_cesa": bool(self.esa_cesa),
            },
            "ocr_quality": self.ocr_quality,
            "meta": {
                "source_pdf_path": self.source_pdf_path,
                "extraction_engine_version": self.extraction_engine_version,
            },
        }
