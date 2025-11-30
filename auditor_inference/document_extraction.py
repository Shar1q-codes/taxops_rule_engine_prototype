"""Document extraction utilities for PDFs, images, and JSON tax documents.

Dependencies for PDF extraction (install as needed):
  pip install pdfplumber  # preferred
  # or
  pip install pypdf

Dependencies for image OCR (install as needed):
  pip install pillow pytesseract
"""

from __future__ import annotations

import io
import json
import logging
import re
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Tuple
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)

def safe_float(val: Any, default: float = 0.0) -> float:
    """Parse a float safely, stripping commas and handling empty values."""
    if val is None:
        return float(default)
    try:
        if isinstance(val, str):
            cleaned = val.replace("$", "").replace(",", "").strip()
            if cleaned.startswith("(") and cleaned.endswith(")"):
                cleaned = f"-{cleaned[1:-1].strip()}"
            if not cleaned:
                return float(default)
            val = cleaned
        return float(val)
    except Exception:
        logger.warning("Failed to parse numeric value %r; defaulting to %s", val, default)
        return float(default)


def load_json_document(path: str | Path) -> Dict[str, Any]:
    """Load a JSON document file."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as handle:
        doc = json.load(handle)
    if not isinstance(doc, dict):
        raise ValueError(f"Expected JSON object in {p}")
    return doc


def extract_text_from_pdf(path_or_stream: str | Path | BytesIO) -> Tuple[str, bool]:
    """Extract text from PDF using pdfplumber or PyPDF2, with OCR fallback."""
    text = ""
    used_ocr = False
    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(path_or_stream) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except ImportError:
        text = ""
    except Exception as exc:
        logger.warning("pdfplumber extraction failed: %s", exc)
        text = ""

    if not text or len(text.strip()) < 50:
        # Fallback: try PyPDF2 text extraction
        try:
            from PyPDF2 import PdfReader  # type: ignore

            reader = PdfReader(path_or_stream)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            logger.warning("PyPDF2 extraction failed: %s", exc)
            text = ""

    if not text or len(text.strip()) < 50:
        # Last resort: OCR each page if pdf2image + pytesseract are available
        try:
            from pdf2image import convert_from_path, convert_from_bytes  # type: ignore
            from PIL import Image  # type: ignore
            import pytesseract  # type: ignore

            if isinstance(path_or_stream, (str, Path)):
                images = convert_from_path(str(path_or_stream), dpi=200)
            else:
                raw = path_or_stream.read() if hasattr(path_or_stream, "read") else path_or_stream
                images = convert_from_bytes(raw, dpi=200)
            ocr_texts = [pytesseract.image_to_string(img) for img in images]
            text = "\n".join(ocr_texts)
            used_ocr = True
        except Exception as exc:
            logger.warning("OCR extraction failed: %s", exc)
            # If OCR dependencies not available, keep whatever text we have (possibly empty)
            pass

    return text, used_ocr


def extract_structured_fields(text: str) -> Dict[str, Any]:
    """Very lightweight heuristic extraction for SSN/EIN/tax year mentions."""
    fields: Dict[str, Any] = {}
    ssn_match = re.search(r"\b(\d{3}-\d{2}-\d{4})\b", text)
    ein_match = re.search(r"\b(\d{2}-\d{7})\b", text)
    year_matches = re.findall(r"\b(20\d{2})\b", text)
    if ssn_match:
        fields["employee"] = {"ssn": ssn_match.group(1)}
    if ein_match:
        fields.setdefault("employer", {})["ein"] = ein_match.group(1)
    if year_matches:
        fields["detected_years"] = [int(y) for y in year_matches]
        fields["tax_year"] = int(year_matches[0])
    return fields


def _detect_form_type_from_text(text: str) -> str:
    upper = (text or "").upper()
    if "FORM 5498" in upper or "5498" in upper:
        return "5498"
    if "1099-SA" in upper or "FORM 1099-SA" in upper:
        return "1099-SA"
    if "1099-C" in upper or "FORM 1099-C" in upper or "CANCELLATION OF DEBT" in upper:
        return "1099-C"
    if "1099-S" in upper or "FORM 1099-S" in upper:
        return "1099-S"
    if "1099-G" in upper or "FORM 1099-G" in upper:
        return "1099-G"
    if "1098-T" in upper or "TUITION STATEMENT" in upper or "FORM 1098-T" in upper:
        return "1098-T"
    if "1099-INT" in upper or "FORM 1099-INT" in upper:
        return "1099-INT"
    if "1099-NEC" in upper or "NONEMPLOYEE COMPENSATION" in upper:
        return "1099-NEC"
    if "1099-MISC" in upper or "MISCELLANEOUS INCOME" in upper:
        return "1099-MISC"
    if "1099-DIV" in upper or "DIVIDENDS" in upper:
        return "1099-DIV"
    if "1099-K" in upper or "PAYMENT CARD" in upper or "THIRD PARTY NETWORK" in upper:
        return "1099-K"
    if "1099-R" in upper or "RETIREMENT" in upper:
        return "1099-R"
    if "1098" in upper and "MORTGAGE" in upper:
        return "1098"
    if "1095-A" in upper or "HEALTH INSURANCE MARKETPLACE" in upper:
        return "1095-A"
    if "FORM 941" in upper or "EMPLOYER'S QUARTERLY FEDERAL TAX RETURN" in upper:
        return "941"
    if "FORM W-9" in upper or "REQUEST FOR TAXPAYER IDENTIFICATION NUMBER" in upper:
        return "W-9"
    if "SSA-1099" in upper or "SOCIAL SECURITY BENEFIT STATEMENT" in upper:
        return "SSA-1099"
    return "W2"


def extract_acroform_fields(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Attempt to extract AcroForm field names and values from an interactive / fillable W-2 PDF.
    Returns a flat dict mapping field_name -> string_value.
    """
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:
        logger.warning("Failed to read PDF for AcroForm extraction: %s", exc)
        return {}

    fields: Dict[str, Any] = {}
    try:
        raw_fields = reader.get_fields()
        if not raw_fields:
            return {}
        for name, field in raw_fields.items():
            value = field.get("/V")
            if value is None:
                continue
            if isinstance(value, str):
                fields[name] = value.strip()
            else:
                fields[name] = str(value).strip()
    except Exception as exc:
        logger.warning("Error while extracting AcroForm fields: %s", exc)
        return {}

    return fields


def map_w2_fields_from_form(form_fields: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map common W-2 interactive/form field names into our normalized W-2 structure.
    This is a best-effort mapping for typical interactive W-2 PDFs (e.g., ADP, payroll vendors).
    """

    def get_first(*keys: str, default: str | None = None) -> str | None:
        for k in keys:
            if k in form_fields and str(form_fields[k]).strip():
                return str(form_fields[k]).strip()
        return default

    ssn = get_first("EmployeeSSN", "EmpSSN", "SSN", "f1_8", "SSN_1")
    ein = get_first("EmployerEIN", "EIN", "EmpEIN", "f1_2", "EIN_1")

    def parse_float(val: Any) -> float:
        return safe_float(val, 0.0)

    wages_box1 = parse_float(get_first("WagesTipsOther", "Wages_Tips", "Box1", "W2_Box1"))
    fit_box2 = parse_float(get_first("FedIncomeTaxWithheld", "Box2", "W2_Box2"))
    ss_wages_b3 = parse_float(get_first("SocialSecurityWages", "Box3", "W2_Box3"))
    ss_tax_b4 = parse_float(get_first("SocialSecurityTax", "Box4", "W2_Box4"))
    med_wages_b5 = parse_float(get_first("MedicareWages", "Box5", "W2_Box5"))
    med_tax_b6 = parse_float(get_first("MedicareTax", "Box6", "W2_Box6"))
    state_wages = parse_float(get_first("StateWages", "Box16", "W2_Box16"))
    state_tax = parse_float(get_first("StateIncomeTax", "Box17", "W2_Box17"))

    tax_year_str = get_first("TaxYear", "Year", "W2_Year")
    tax_year = None
    if tax_year_str:
        try:
            tax_year = int(str(tax_year_str).strip())
        except ValueError:
            tax_year = None

    logger.info(
        "W-2 form-field mapping applied: wages_box1=%s, fit=%s, ss_wages=%s",
        wages_box1,
        fit_box2,
        ss_wages_b3,
    )

    return {
        "employee": {
            "ssn": ssn,
        },
        "employer": {
            "ein": ein,
        },
        "wages": {
            "wages_tips_other": wages_box1,
            "federal_income_tax_withheld": fit_box2,
            "social_security_wages": ss_wages_b3,
            "social_security_tax_withheld": ss_tax_b4,
            "medicare_wages": med_wages_b5,
            "medicare_tax_withheld": med_tax_b6,
        },
        "state": {
            "state_wages": state_wages,
            "state_tax_withheld": state_tax,
        },
        "tax_year": tax_year,
    }


def map_1099int_fields_from_form(form_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Map common 1099-INT form fields to our normalized structure."""

    def get_first(*keys: str, default: str | None = None) -> str | None:
        for k in keys:
            if k in form_fields and str(form_fields[k]).strip():
                return str(form_fields[k]).strip()
        return default

    def parse_float(val: Any) -> float:
        return safe_float(val, 0.0)

    payer_tin = get_first("PayerTIN", "PAYER_TIN", "PayerTIN1", "f1_1")
    recipient_tin = get_first("RecipientTIN", "RECIPIENT_TIN", "f1_8")
    tax_year = get_first("TaxYear", "Year", "f1_11")
    try:
        tax_year_int = int(tax_year) if tax_year else None
    except Exception:
        tax_year_int = None

    def box(*keys: str) -> float:
        return parse_float(get_first(*keys))

    return {
        "tax_year": tax_year_int,
        "payer": {"tin": payer_tin},
        "recipient": {"tin": recipient_tin},
        "amounts": {
            "box_1_interest_income": box("Box1", "InterestIncome"),
            "box_2_early_withdrawal_penalty": box("Box2", "EarlyWithdrawalPenalty"),
            "box_3_us_savings_bonds_and_treasury_interest": box("Box3"),
            "box_4_federal_income_tax_withheld": box("Box4"),
            "box_5_investment_expenses": box("Box5"),
            "box_6_foreign_tax_paid": box("Box6"),
            "box_8_tax_exempt_interest": box("Box8"),
            "box_9_specified_private_activity_bond_interest": box("Box9"),
            "box_10_market_discount": box("Box10"),
            "box_11_bond_premium": box("Box11"),
        },
    }


def map_1099nec_fields_from_form(form_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Map common 1099-NEC form fields to our normalized structure."""

    def get_first(*keys: str, default: str | None = None) -> str | None:
        for k in keys:
            if k in form_fields and str(form_fields[k]).strip():
                return str(form_fields[k]).strip()
        return default

    def parse_float(val: Any) -> float:
        return safe_float(val, 0.0)

    payer_tin = get_first("PayerTIN", "PAYER_TIN", "f1_1")
    recipient_tin = get_first("RecipientTIN", "RECIPIENT_TIN", "f1_8")
    tax_year = get_first("TaxYear", "Year", "f1_11")
    try:
        tax_year_int = int(tax_year) if tax_year else None
    except Exception:
        tax_year_int = None

    return {
        "tax_year": tax_year_int,
        "payer": {"tin": payer_tin},
        "recipient": {"tin": recipient_tin},
        "amounts": {
            "box_1_nonemployee_compensation": parse_float(get_first("Box1", "NonemployeeComp", "NonemployeeCompensation")),
            "box_4_federal_income_tax_withheld": parse_float(get_first("Box4", "FedTaxWithheld")),
            "box_5_state_tax_withheld_total": parse_float(get_first("Box5", "StateTaxWithheld")),
        },
    }

def map_1099misc_fields_from_form(form_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Map common 1099-MISC form fields to our normalized structure."""

    def get_first(*keys: str, default: str | None = None) -> str | None:
        for k in keys:
            if k in form_fields and str(form_fields[k]).strip():
                return str(form_fields[k]).strip()
        return default

    def parse_float(val: Any) -> float:
        return safe_float(val, 0.0)

    payer_tin = get_first("PayerTIN", "PAYER_TIN", "f1_1")
    recipient_tin = get_first("RecipientTIN", "RECIPIENT_TIN", "f1_8")
    tax_year = get_first("TaxYear", "Year", "f1_11")
    try:
        tax_year_int = int(tax_year) if tax_year else None
    except Exception:
        tax_year_int = None

    return {
        "tax_year": tax_year_int,
        "payer": {"tin": payer_tin},
        "recipient": {"tin": recipient_tin},
        "amounts": {
            "box_1_rents": parse_float(get_first("Box1", "Rents")),
            "box_2_royalties": parse_float(get_first("Box2", "Royalties")),
            "box_3_other_income": parse_float(get_first("Box3", "OtherIncome")),
            "box_4_federal_income_tax_withheld": parse_float(get_first("Box4", "FedTaxWithheld")),
            "box_6_medical_healthcare_payments": parse_float(get_first("Box6", "MedicalHealthcarePayments")),
            "box_10_gross_proceeds_paid_to_attorney": parse_float(get_first("Box10", "GrossProceedsAttorney")),
        },
    }

def map_1099div_fields_from_form(form_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Map common 1099-DIV form fields to our normalized structure."""

    def get_first(*keys: str, default: str | None = None) -> str | None:
        for k in keys:
            if k in form_fields and str(form_fields[k]).strip():
                return str(form_fields[k]).strip()
        return default

    def parse_float(val: Any) -> float:
        return safe_float(val, 0.0)

    payer_tin = get_first("PayerTIN", "PAYER_TIN", "f1_1")
    recipient_tin = get_first("RecipientTIN", "RECIPIENT_TIN", "f1_8")
    tax_year = get_first("TaxYear", "Year", "f1_11")
    try:
        tax_year_int = int(tax_year) if tax_year else None
    except Exception:
        tax_year_int = None

    def box(*keys: str) -> float:
        return parse_float(get_first(*keys))

    return {
        "tax_year": tax_year_int,
        "payer": {"tin": payer_tin},
        "recipient": {"tin": recipient_tin},
        "amounts": {
            "box_1a_total_ordinary_dividends": box("Box1a", "OrdinaryDividends"),
            "box_1b_qualified_dividends": box("Box1b", "QualifiedDividends"),
            "box_2a_total_capital_gain_distributions": box("Box2a", "CapitalGainDistributions"),
            "box_4_federal_income_tax_withheld": box("Box4", "FedTaxWithheld"),
            "box_6_foreign_tax_paid": box("Box6", "ForeignTaxPaid"),
            "box_11_section_199a_dividends": box("Box11", "Section199ADividends"),
            "box_12_exempt_interest_dividends": box("Box12", "ExemptInterestDividends"),
            "box_13_specified_private_activity_bond_interest_dividends": box("Box13", "PrivateActivityBondInterest"),
        },
        "box_7_foreign_country_or_possession": get_first("Box7", "ForeignCountry"),
    }

def map_1099k_fields_from_form(form_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Map common 1099-K form fields to our normalized structure."""

    def get_first(*keys: str, default: str | None = None) -> str | None:
        for k in keys:
            if k in form_fields and str(form_fields[k]).strip():
                return str(form_fields[k]).strip()
        return default

    def parse_float(val: Any) -> float:
        return safe_float(val, 0.0)

    payer_tin = get_first("PayerTIN", "PAYER_TIN", "f1_1")
    recipient_tin = get_first("PayeeTIN", "RecipientTIN", "RECIPIENT_TIN", "f1_8")
    tax_year = get_first("TaxYear", "Year", "f1_11")
    try:
        tax_year_int = int(tax_year) if tax_year else None
    except Exception:
        tax_year_int = None

    months = []
    for idx in range(1, 13):
        key = f"Month{idx}"
        months.append(parse_float(get_first(key, f"Box5{idx}", f"m{idx}")))

    return {
        "tax_year": tax_year_int,
        "payer": {"tin": payer_tin},
        "recipient": {"tin": recipient_tin},
        "amounts": {
            "box_1a_gross_amount": parse_float(get_first("Box1a", "GrossAmount")),
            "box_1b_card_not_present": parse_float(get_first("Box1b", "CardNotPresent")),
            "box_3_number_of_payment_transactions": parse_float(get_first("Box3", "NumberOfPaymentTransactions")),
            "box_4_federal_income_tax_withheld": parse_float(get_first("Box4", "FedTaxWithheld")),
            "monthly_totals": months,
        },
        "box_2_merchant_category_code": get_first("Box2", "MCC") or "",
        "account_number": get_first("AccountNumber", "AcctNum") or "",
    }

def map_1099r_fields_from_form(form_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Map common 1099-R form fields to our normalized structure."""

    def get_first(*keys: str, default: str | None = None) -> str | None:
        for k in keys:
            if k in form_fields and str(form_fields[k]).strip():
                return str(form_fields[k]).strip()
        return default

    def parse_float(val: Any) -> float:
        return safe_float(val, 0.0)

    payer_tin = get_first("PayerTIN", "PAYER_TIN", "f1_1")
    recipient_tin = get_first("RecipientTIN", "RECIPIENT_TIN", "f1_8")
    tax_year = get_first("TaxYear", "Year", "f1_11")
    try:
        tax_year_int = int(tax_year) if tax_year else None
    except Exception:
        tax_year_int = None

    raw_codes = get_first("Box7", "DistributionCodes") or ""
    codes = [c.strip() for c in re.split(r"[ ,/]+", raw_codes) if c.strip()]

    ira_indicator = False
    ira_flag = get_first("IRAIndicator", "IRA", "IRABox")
    if ira_flag and str(ira_flag).strip().lower() in {"1", "true", "yes", "y"}:
        ira_indicator = True

    taxable_not_determined = False
    tnd = get_first("Box2bTaxableNotDetermined", "TaxableAmountNotDetermined")
    if tnd and str(tnd).strip().lower() in {"1", "true", "yes", "y"}:
        taxable_not_determined = True

    return {
        "tax_year": tax_year_int,
        "payer": {"tin": payer_tin},
        "recipient": {"tin": recipient_tin},
        "account_number": get_first("AccountNumber", "AcctNum") or "",
        "box_2b_taxable_amount_not_determined": taxable_not_determined,
        "box_7_distribution_codes": codes,
        "box_7_ira_sep_simple_indicator": ira_indicator,
        "amounts": {
            "box_1_gross_distribution": parse_float(get_first("Box1", "GrossDistribution")),
            "box_2a_taxable_amount": parse_float(get_first("Box2a", "TaxableAmount")),
            "box_3_capital_gain_included": parse_float(get_first("Box3", "CapitalGain")),
            "box_4_federal_income_tax_withheld": parse_float(get_first("Box4", "FedTaxWithheld")),
            "box_5_employee_contributions_or_insurance_premiums": parse_float(get_first("Box5", "EmployeeContributions")),
            "box_9b_total_employee_contributions": parse_float(get_first("Box9b", "TotalEmployeeContributions")),
            "box_10_amount_allocable_to_IRR": parse_float(get_first("Box10", "AmountAllocableToIRR")),
        },
    }

def map_1098_fields_from_form(form_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Map common 1098 form fields to our normalized structure."""

    def get_first(*keys: str, default: str | None = None) -> str | None:
        for k in keys:
            if k in form_fields and str(form_fields[k]).strip():
                return str(form_fields[k]).strip()
        return default

    def parse_float(val: Any) -> float:
        return safe_float(val, 0.0)

    payer_tin = get_first("LenderTIN", "PayerTIN", "PAYER_TIN", "f1_1")
    recipient_tin = get_first("BorrowerTIN", "RECIPIENT_TIN", "f1_8")
    tax_year = get_first("TaxYear", "Year", "f1_11")
    try:
        tax_year_int = int(tax_year) if tax_year else None
    except Exception:
        tax_year_int = None

    return {
        "tax_year": tax_year_int,
        "payer": {"tin": payer_tin},
        "recipient": {"tin": recipient_tin},
        "amounts": {
            "box_1_mortgage_interest_received": parse_float(get_first("Box1", "InterestReceived")),
            "box_2_outstanding_mortgage_principal": parse_float(get_first("Box2", "OutstandingPrincipal")),
            "box_4_refunded_interest": parse_float(get_first("Box4", "RefundedInterest")),
            "box_5_mortgage_insurance_premiums": parse_float(get_first("Box5", "MortgageInsurancePremiums")),
            "box_6_points_paid_on_purchase": parse_float(get_first("Box6", "PointsPaid")),
        },
        "box_3_mortgage_origination_date": get_first("Box3", "OriginationDate") or "",
        "box_7_mortgaged_property_address": get_first("Box7", "PropertyAddress") or "",
        "box_8_mortgaged_property_account_number": get_first("Box8", "AccountNumber") or "",
        "box_9_additional_mortgaged_property_info": get_first("Box9", "AdditionalPropertyInfo") or "",
    }

def map_1095a_fields_from_form(form_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Map common 1095-A form fields to our normalized structure."""

    def get_first(*keys: str, default: str | None = None) -> str | None:
        for k in keys:
            if k in form_fields and str(form_fields[k]).strip():
                return str(form_fields[k]).strip()
        return default

    def parse_float(val: Any) -> float:
        return safe_float(val, 0.0)

    recipient_tin = get_first("RecipientTIN", "RECIPIENT_TIN", "SSN", "f1_8")
    tax_year = get_first("TaxYear", "Year", "f1_11")
    try:
        tax_year_int = int(tax_year) if tax_year else None
    except Exception:
        tax_year_int = None

    months = []
    for idx in range(1, 13):
        months.append(
            {
                "month_index": idx,
                "monthly_premium": parse_float(get_first(f"BoxA{idx}", f"MonthlyPremium{idx}")),
                "slcsp_premium": parse_float(get_first(f"BoxB{idx}", f"SLCSP{idx}")),
                "advance_premium_tax_credit": parse_float(get_first(f"BoxC{idx}", f"APTC{idx}")),
            }
        )

    return {
        "tax_year": tax_year_int,
        "recipient": {"tin": recipient_tin},
        "issuer": {"name": get_first("IssuerName", "MarketplaceName") or ""},
        "months": months,
    }

def map_941_fields_from_form(form_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Map common 941 form fields to our normalized structure."""

    def get_first(*keys: str, default: str | None = None) -> str | None:
        for k in keys:
            if k in form_fields and str(form_fields[k]).strip():
                return str(form_fields[k]).strip()
        return default

    def parse_float(val: Any) -> float:
        return safe_float(val, 0.0)

    employer_ein = get_first("EIN", "EmployerEIN", "f1_2")
    tax_year = get_first("TaxYear", "Year")
    tax_quarter = get_first("TaxQuarter", "Quarter")
    try:
        tax_year_int = int(tax_year) if tax_year else None
    except Exception:
        tax_year_int = None
    try:
        tax_quarter_int = int(tax_quarter) if tax_quarter else None
    except Exception:
        tax_quarter_int = None

    return {
        "tax_year": tax_year_int,
        "tax_quarter": tax_quarter_int,
        "employer": {"ein": employer_ein},
        "amounts": {
            "line_1_num_employees": parse_float(get_first("Line1", "NumEmployees")),
            "line_2_wages_tips_other_comp": parse_float(get_first("Line2", "WagesTipsOtherComp")),
            "line_3_income_tax_withheld": parse_float(get_first("Line3", "IncomeTaxWithheld")),
            "line_5a_taxable_ss_wages": parse_float(get_first("Line5a", "TaxableSSWages")),
            "line_5a_ss_tax": parse_float(get_first("Line5aTax", "SSTax")),
            "line_5b_taxable_ss_tips": parse_float(get_first("Line5b", "TaxableSSTips")),
            "line_5b_ss_tax_tips": parse_float(get_first("Line5bTax", "SSTaxTips")),
            "line_5c_taxable_medicare_wages": parse_float(get_first("Line5c", "TaxableMedicareWages")),
            "line_5c_medicare_tax": parse_float(get_first("Line5cTax", "MedicareTax")),
            "line_5d_taxable_addl_medicare_wages": parse_float(get_first("Line5d", "TaxableAddlMedicareWages")),
            "line_5d_addl_medicare_tax": parse_float(get_first("Line5dTax", "AddlMedicareTax")),
            "line_6_total_taxes_before_adjustments": parse_float(get_first("Line6", "TotalTaxesBeforeAdj")),
            "line_7_current_quarter_fractions_of_cents_adjustment": parse_float(get_first("Line7", "FractionsOfCentsAdj")),
            "line_8_tip_adjustment": parse_float(get_first("Line8", "TipAdjustment")),
            "line_9_sick_pay_adjustment": parse_float(get_first("Line9", "SickPayAdjustment")),
            "line_10_total_taxes_after_adjustments": parse_float(get_first("Line10", "TotalTaxesAfterAdj")),
            "line_11_total_deposits_for_quarter": parse_float(get_first("Line11", "TotalDeposits")),
            "line_12_refundable_credits": parse_float(get_first("Line12", "RefundableCredits")),
            "line_13_total_taxes_after_credits": parse_float(get_first("Line13", "TotalTaxesAfterCredits")),
            "line_14_balance_due": parse_float(get_first("Line14", "BalanceDue")),
            "line_15_overpayment": parse_float(get_first("Line15", "Overpayment")),
        },
    }

def map_w9_fields_from_form(form_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Map common W-9 form fields to our normalized structure."""

    def get_first(*keys: str, default: str | None = None) -> str | None:
        for k in keys:
            if k in form_fields and str(form_fields[k]).strip():
                return str(form_fields[k]).strip()
        return default

    classification_keys = {
        "individual/sole proprietor": ["Individual", "SoleProprietor"],
        "c corporation": ["CCorporation", "C Corp"],
        "s corporation": ["SCorporation", "S Corp"],
        "partnership": ["Partnership"],
        "trust/estate": ["Trust", "Estate"],
        "llc": ["LLC"],
        "other": ["Other"],
    }
    federal_tax_classification = get_first("FederalTaxClassification", "TaxClassification", "Class")
    if not federal_tax_classification:
        for label, keys in classification_keys.items():
            if any(k in form_fields and str(form_fields[k]).strip() for k in keys):
                federal_tax_classification = label
                break

    return {
        "taxpayer_name": get_first("TaxpayerName", "Name", "Line1") or "",
        "business_name_disregarded": get_first("BusinessName", "Line2") or "",
        "federal_tax_classification": federal_tax_classification or "",
        "llc_tax_class_code": get_first("LLCTaxClass", "LLCClass") or "",
        "exempt_payee_code": get_first("ExemptPayeeCode") or "",
        "fatca_exemption_code": get_first("FATCAExemptionCode") or "",
        "address_line1": get_first("Address1", "Street") or "",
        "address_line2": get_first("Address2") or "",
        "city": get_first("City") or "",
        "state": get_first("State") or "",
        "zip_code": get_first("ZIP", "Zip") or "",
        "ssn": get_first("SSN") or "",
        "ein": get_first("EIN") or "",
        "tin_raw": get_first("TIN") or "",
        "certification_signed_flag": str(get_first("CertificationSigned", "Signature", "Signed") or "").strip().lower() in {"1", "true", "yes", "y"},
    }

def extract_box_value(text: str, label: str) -> float:
    """Extract numeric value following a W-2 box label."""
    pattern = rf"{re.escape(label)}\s*[:\-]?\s*\$?([\d,]+(?:\.\d+)?)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return 0.0
    return safe_float(match.group(1), 0.0)


def extract_clause_indicators(text: str) -> List[str]:
    """Detect simple clause indicators (e.g., withholding, exemption)."""
    indicators = []
    lowered = text.lower()
    if "withholding" in lowered:
        indicators.append("withholding")
    if "exempt" in lowered:
        indicators.append("exemption")
    if "penalty" in lowered:
        indicators.append("penalty")
    return indicators


def extract_text_from_image(path: str | Path) -> str:
    """Extract text from common image formats using Tesseract if available."""
    try:
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError("Install pillow and pytesseract for image OCR.") from exc

    with Image.open(path) as img:
        return pytesseract.image_to_string(img)


def extract_text_from_image_bytes(data: bytes) -> str:
    """Extract text from in-memory image bytes."""
    try:
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError("Install pillow and pytesseract for image OCR.") from exc

    with Image.open(BytesIO(data)) as img:
        return pytesseract.image_to_string(img)


def _blank_w2(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "form_type": "W2",
        "doc_type": "W2",
        "employee": {"first_name": "", "last_name": "", "ssn": ""},
        "employer": {"name": "", "ein": ""},
        "wages": {
            "wages_tips_other": 0.0,
            "federal_income_tax_withheld": 0.0,
            "social_security_wages": 0.0,
            "social_security_tax_withheld": 0.0,
            "medicare_wages": 0.0,
            "medicare_tax_withheld": 0.0,
        },
        "state": {"state_code": "", "state_wages": 0.0, "state_tax_withheld": 0.0},
        "tax_year": None,
        "ocr_quality": 1.0,
    }


def _blank_1099int(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_type": "1099-INT",
        "tax_year": None,
        "payer": {"name": "", "tin": "", "address": ""},
        "recipient": {"name": "", "tin": "", "address": ""},
        "account_number": "",
        "amounts": {
            "box_1_interest_income": 0.0,
            "box_2_early_withdrawal_penalty": 0.0,
            "box_3_us_savings_bonds_and_treasury_interest": 0.0,
            "box_4_federal_income_tax_withheld": 0.0,
            "box_5_investment_expenses": 0.0,
            "box_6_foreign_tax_paid": 0.0,
            "box_8_tax_exempt_interest": 0.0,
            "box_9_specified_private_activity_bond_interest": 0.0,
            "box_10_market_discount": 0.0,
            "box_11_bond_premium": 0.0,
        },
        "state_items": [],
        "ocr_quality": 1.0,
    }

def _blank_1099nec(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_type": "1099-NEC",
        "tax_year": None,
        "payer": {"name": "", "tin": "", "address": ""},
        "recipient": {"name": "", "tin": "", "address": ""},
        "amounts": {
            "box_1_nonemployee_compensation": 0.0,
            "box_4_federal_income_tax_withheld": 0.0,
            "box_5_state_tax_withheld_total": 0.0,
        },
        "state_items": [],
        "ocr_quality": 1.0,
    }

def _blank_1099misc(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_type": "1099-MISC",
        "tax_year": None,
        "payer": {"name": "", "tin": "", "address": ""},
        "recipient": {"name": "", "tin": "", "address": ""},
        "amounts": {
            "box_1_rents": 0.0,
            "box_2_royalties": 0.0,
            "box_3_other_income": 0.0,
            "box_4_federal_income_tax_withheld": 0.0,
            "box_6_medical_healthcare_payments": 0.0,
            "box_10_gross_proceeds_paid_to_attorney": 0.0,
        },
        "state_items": [],
        "ocr_quality": 1.0,
    }

def _blank_1099div(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_type": "1099-DIV",
        "tax_year": None,
        "payer": {"name": "", "tin": "", "address": ""},
        "recipient": {"name": "", "tin": "", "address": ""},
        "amounts": {
            "box_1a_total_ordinary_dividends": 0.0,
            "box_1b_qualified_dividends": 0.0,
            "box_2a_total_capital_gain_distributions": 0.0,
            "box_4_federal_income_tax_withheld": 0.0,
            "box_6_foreign_tax_paid": 0.0,
            "box_11_section_199a_dividends": 0.0,
            "box_12_exempt_interest_dividends": 0.0,
            "box_13_specified_private_activity_bond_interest_dividends": 0.0,
        },
        "state_items": [],
        "box_7_foreign_country_or_possession": "",
        "ocr_quality": 1.0,
    }

def _blank_1099k(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_type": "1099-K",
        "tax_year": None,
        "payer": {"name": "", "tin": "", "address": ""},
        "recipient": {"name": "", "tin": "", "address": ""},
        "account_number": "",
        "amounts": {
            "box_1a_gross_amount": 0.0,
            "box_1b_card_not_present": 0.0,
            "box_3_number_of_payment_transactions": 0.0,
            "box_4_federal_income_tax_withheld": 0.0,
            "monthly_totals": [0.0] * 12,
        },
        "box_2_merchant_category_code": "",
        "state_items": [],
        "ocr_quality": 1.0,
    }

def _blank_1099r(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_type": "1099-R",
        "tax_year": None,
        "payer": {"name": "", "tin": "", "address": ""},
        "recipient": {"name": "", "tin": "", "address": ""},
        "account_number": "",
        "amounts": {
            "box_1_gross_distribution": 0.0,
            "box_2a_taxable_amount": 0.0,
            "box_3_capital_gain_included": 0.0,
            "box_4_federal_income_tax_withheld": 0.0,
            "box_5_employee_contributions_or_insurance_premiums": 0.0,
            "box_6_net_unrealized_appreciation": 0.0,
            "box_8_other": 0.0,
            "box_9a_total_distribution_pct": 0.0,
            "box_9b_total_employee_contributions": 0.0,
            "box_10_amount_allocable_to_IRR": 0.0,
        },
        "box_2b_taxable_amount_not_determined": False,
        "box_2b_total_distribution": False,
        "box_7_distribution_codes": [],
        "box_7_ira_sep_simple_indicator": False,
        "box_11_first_year_designated_roth": None,
        "box_12_fatca_filing_requirement": False,
        "box_13_date_of_payment": "",
        "box_14_state_tax_withheld": [],
        "box_15_state_id": [],
        "box_16_state_distribution": [],
        "state_items": [],
        "ocr_quality": 1.0,
    }

def _blank_1099g(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_type": "1099-G",
        "tax_year": None,
        "payer": {"name": "", "tin": "", "address": ""},
        "recipient": {"name": "", "tin": "", "address": ""},
        "account_number": "",
        "amounts": {
            "box1_unemployment_compensation": 0.0,
            "box2_state_local_tax_refunds": 0.0,
            "box4_federal_income_tax_withheld": 0.0,
            "box5_rtaa_payments": 0.0,
            "box6_taxable_grants": 0.0,
            "box7_agricultural_payments": 0.0,
            "box9_market_gain": 0.0,
        },
        "box3_box2_tax_year": None,
        "box8_trade_or_business_indicator": False,
        "box10_state_tax_withheld": [],
        "box11_state_id": [],
        "box12_state_income": [],
        "ocr_quality": 1.0,
    }

def _blank_1099s(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_type": "1099-S",
        "tax_year": None,
        "filer": {"name": "", "tin": "", "address": ""},
        "transferor": {"name": "", "tin": "", "address": ""},
        "account_number": "",
        "property_address": "",
        "property_desc": "",
        "amounts": {
            "box1_gross_proceeds": 0.0,
            "box4_federal_income_tax_withheld": 0.0,
        },
        "box2_property_or_services": False,
        "box3_recipient_is_transferor": False,
        "box5_transferor_is_foreign": False,
        "closing_date": "",
        "state_tax_withheld": [],
        "state_id": [],
        "state_income": [],
        "ocr_quality": 1.0,
    }

def _blank_1099c(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_type": "1099-C",
        "tax_year": None,
        "creditor": {"name": "", "tin": "", "address": ""},
        "debtor": {"name": "", "tin": "", "address": ""},
        "account_number": "",
        "amounts": {
            "box2_amount_of_debt_discharged": 0.0,
            "box3_interest_if_included": 0.0,
            "box7_fair_market_value_property": 0.0,
        },
        "box1_date_of_identifiable_event": "",
        "box4_debt_description": "",
        "box5_debtor_personally_liable": False,
        "box6_identifiable_event_code": "",
        "state_tax_withheld": [],
        "state_id": [],
        "state_income": [],
        "ocr_quality": 1.0,
    }

def _blank_1099sa(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_type": "1099-SA",
        "tax_year": None,
        "payer": {"name": "", "tin": "", "address": ""},
        "recipient": {"name": "", "tin": "", "address": ""},
        "account_number": "",
        "amounts": {
            "box1_gross_distribution": 0.0,
            "box2_earnings_on_excess_contributions": 0.0,
            "box4_federal_income_tax_withheld": 0.0,
            "box5_fair_market_value_hsa_msa": 0.0,
        },
        "box3_distribution_code": "",
        "hsa": False,
        "archer_msa": False,
        "ma_msa": False,
        "state_tax_withheld": [],
        "state_id": [],
        "state_income": [],
        "ocr_quality": 1.0,
    }

def _blank_1099q(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_type": "1099-Q",
        "tax_year": None,
        "payer": {"name": "", "tin": "", "address": ""},
        "recipient": {"name": "", "tin": "", "address": ""},
        "account_number": "",
        "amounts": {
            "box1_gross_distribution": 0.0,
            "box2_earnings": 0.0,
            "box3_basis": 0.0,
        },
        "box4_trustee_to_trustee_transfer": False,
        "box5_qualified_tuition_program": False,
        "box6_life_insurance_distributed": False,
        "qualified_tuition_program_529": False,
        "coverdell_esa": False,
        "state_tax_withheld": [],
        "state_id": [],
        "state_income": [],
        "ocr_quality": 1.0,
    }

def _blank_5498(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_type": "5498",
        "tax_year": None,
        "trustee": {"name": "", "tin": "", "address": ""},
        "participant": {"name": "", "tin": "", "address": ""},
        "account_number": "",
        "amounts": {
            "box1_ira_contributions": 0.0,
            "box2_rollover_contributions": 0.0,
            "box3_roth_ira_conversion_amount": 0.0,
            "box4_recharacterized_contributions": 0.0,
            "box5_fmv_of_account": 0.0,
            "box6_life_insurance_cost_in_ira": 0.0,
            "box7_roth_ira_contributions": 0.0,
            "box8_sep_contributions": 0.0,
            "box9_simple_contributions": 0.0,
            "box10_roth_ira_fmv_rollovers": 0.0,
            "box13_rmd_amount": 0.0,
            "box14_hsa_msa_contributions": 0.0,
            "box15_other_contributions": 0.0,
        },
        "box11_required_minimum_distribution_indicator": False,
        "box12_rmd_date": "",
        "flags": {
            "traditional_ira": False,
            "roth_ira": False,
            "sep_ira": False,
            "simple_ira": False,
            "hsa": False,
            "esa_cesa": False,
        },
        "ocr_quality": 1.0,
    }

def _blank_1098(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_type": "1098",
        "tax_year": None,
        "payer": {"name": "", "tin": "", "address": ""},
        "recipient": {"name": "", "tin": "", "address": ""},
        "amounts": {
            "box_1_mortgage_interest_received": 0.0,
            "box_2_outstanding_mortgage_principal": 0.0,
            "box_4_refunded_interest": 0.0,
            "box_5_mortgage_insurance_premiums": 0.0,
            "box_6_points_paid_on_purchase": 0.0,
        },
        "box_3_mortgage_origination_date": "",
        "box_7_mortgaged_property_address": "",
        "box_8_mortgaged_property_account_number": "",
        "box_9_additional_mortgaged_property_info": "",
        "ocr_quality": 1.0,
    }

def _blank_1095a(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_type": "1095-A",
        "tax_year": None,
        "issuer": {"name": "", "ein": "", "address": ""},
        "recipient": {"name": "", "tin": "", "address": ""},
        "covered_individuals": [],
        "months": [],
        "ocr_quality": 1.0,
    }

def _blank_941(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_type": "941",
        "tax_year": None,
        "tax_quarter": None,
        "employer": {"name": "", "ein": "", "address": ""},
        "amounts": {
            "line_1_num_employees": 0.0,
            "line_2_wages_tips_other_comp": 0.0,
            "line_3_income_tax_withheld": 0.0,
            "line_5a_taxable_ss_wages": 0.0,
            "line_5a_ss_tax": 0.0,
            "line_5b_taxable_ss_tips": 0.0,
            "line_5b_ss_tax_tips": 0.0,
            "line_5c_taxable_medicare_wages": 0.0,
            "line_5c_medicare_tax": 0.0,
            "line_5d_taxable_addl_medicare_wages": 0.0,
            "line_5d_addl_medicare_tax": 0.0,
            "line_6_total_taxes_before_adjustments": 0.0,
            "line_7_current_quarter_fractions_of_cents_adjustment": 0.0,
            "line_8_tip_adjustment": 0.0,
            "line_9_sick_pay_adjustment": 0.0,
            "line_10_total_taxes_after_adjustments": 0.0,
            "line_11_total_deposits_for_quarter": 0.0,
            "line_12_refundable_credits": 0.0,
            "line_13_total_taxes_after_credits": 0.0,
            "line_14_balance_due": 0.0,
            "line_15_overpayment": 0.0,
        },
        "ocr_quality": 1.0,
    }

def _blank_w9(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_type": "W-9",
        "tax_year": None,
        "requestor_name": "",
        "taxpayer_name": "",
        "business_name_disregarded": "",
        "federal_tax_classification": "",
        "llc_tax_class_code": "",
        "exempt_payee_code": "",
        "fatca_exemption_code": "",
        "address_line1": "",
        "address_line2": "",
        "city": "",
        "state": "",
        "zip_code": "",
        "ssn": "",
        "ein": "",
        "tin_raw": "",
        "certification_signed_flag": False,
        "certification_date": "",
        "ocr_quality": 1.0,
    }


def _apply_extracted_fields(doc: Dict[str, Any], extracted: Dict[str, Any]) -> None:
    if not extracted:
        return
    employee = extracted.get("employee") or {}
    employer = extracted.get("employer") or {}
    if "first_name" in employee or "last_name" in employee or "ssn" in employee:
        doc["employee"].update({k: v for k, v in employee.items() if v})
    if employer:
        doc["employer"].update({k: v for k, v in employer.items() if v})
    if "tax_year" in extracted:
        doc["tax_year"] = extracted["tax_year"]


def _assign_ocr_quality(text: str, used_ocr: bool) -> float:
    return 0.7 if used_ocr else 1.0


def _extract_wage_boxes(text: str) -> Dict[str, float]:
    label_sets = {
        ("Box 1", "Box1", "1", "1."): ("wages", "wages_tips_other"),
        ("Box 2", "Box2", "2", "2."): ("wages", "federal_income_tax_withheld"),
        ("Box 3", "Box3", "3", "3."): ("wages", "social_security_wages"),
        ("Box 4", "Box4", "4", "4."): ("wages", "social_security_tax_withheld"),
        ("Box 5", "Box5", "5", "5."): ("wages", "medicare_wages"),
        ("Box 6", "Box6", "6", "6."): ("wages", "medicare_tax_withheld"),
        ("Box 16", "Box16", "16", "16."): ("state", "state_wages"),
        ("Box 17", "Box17", "17", "17."): ("state", "state_tax_withheld"),
    }
    results: Dict[str, float] = {}
    for labels, (section, key) in label_sets.items():
        val = 0.0
        for label in labels:
            val = extract_box_value(text, label)
            if val > 0:
                break
        if val <= 0:
            # Try line-based pattern like "1 Wages, tips, other compensation 50,000.00"
            box_num = re.sub(r"\D", "", labels[0]) or labels[0]
            pattern = rf"^{box_num}\s+[A-Za-z, \-/]+?\s+\$?([\d,]+(?:\.\d+)?)"
            match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
            if match:
                val = safe_float(match.group(1), 0.0)
        if val > 0:
            results[f"{section}.{key}"] = val
    return results


def _fallback_numeric_by_keyword(text: str, keyword: str) -> float:
    pattern = rf"{keyword}.*?\$?([\d,]+(?:\.\d+)?)"
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return safe_float(match.group(1), 0.0)
    return 0.0


def _apply_fallback_amounts(doc: Dict[str, Any], text: str) -> None:
    wages = doc.get("wages") or {}
    mappings = {
        "wages_tips_other": ["wages", "wages tips", "box 1"],
        "federal_income_tax_withheld": ["federal income tax", "federal withholding", "box 2"],
        "social_security_wages": ["social security wages", "box 3"],
        "social_security_tax_withheld": ["social security tax", "box 4"],
        "medicare_wages": ["medicare wages", "box 5"],
        "medicare_tax_withheld": ["medicare tax", "box 6"],
    }
    for field, keywords in mappings.items():
        if safe_float(wages.get(field), 0.0) > 0.0:
            continue
        for kw in keywords:
            val = _fallback_numeric_by_keyword(text, kw)
            if val > 0:
                wages[field] = val
                break
    doc["wages"] = wages


def _populate_wages_from_text(doc: Dict[str, Any], text: str) -> None:
    values = _extract_wage_boxes(text)
    for dotted, val in values.items():
        section, key = dotted.split(".", 1)
        if section not in doc or not isinstance(doc[section], dict):
            continue
        doc[section][key] = val


def _wages_missing(doc: Dict[str, Any]) -> bool:
    wages = doc.get("wages") or {}
    required_keys = [
        "wages_tips_other",
        "federal_income_tax_withheld",
        "social_security_wages",
        "social_security_tax_withheld",
        "medicare_wages",
        "medicare_tax_withheld",
    ]
    return any(safe_float(wages.get(k, 0.0), 0.0) <= 0.0 for k in required_keys)


def _log_missing_fields(doc: Dict[str, Any]) -> None:
    wages = doc.get("wages") or {}
    state = doc.get("state") or {}
    wages_present = safe_float(wages.get("wages_tips_other"), 0.0) > 0.0
    if wages_present:
        checks = [
            ("wages.federal_income_tax_withheld", wages.get("federal_income_tax_withheld")),
            ("wages.social_security_wages", wages.get("social_security_wages")),
            ("wages.social_security_tax_withheld", wages.get("social_security_tax_withheld")),
            ("wages.medicare_wages", wages.get("medicare_wages")),
            ("wages.medicare_tax_withheld", wages.get("medicare_tax_withheld")),
        ]
        for field, value in checks:
            if safe_float(value, 0.0) <= 0.0:
                logger.warning("Missing field: %s", field)

    state_code = state.get("state_code") or ""
    if state_code.strip():
        for field, value in [
            ("state.state_wages", state.get("state_wages")),
            ("state.state_tax_withheld", state.get("state_tax_withheld")),
        ]:
            if safe_float(value, 0.0) <= 0.0:
                logger.warning("Missing field: %s", field)


def _merge_form_mapping(doc: Dict[str, Any], mapped: Dict[str, Any]) -> None:
    if not mapped:
        return
    doc["employee"]["ssn"] = doc["employee"].get("ssn") or mapped.get("employee", {}).get("ssn") or ""
    doc["employer"]["ein"] = doc["employer"].get("ein") or mapped.get("employer", {}).get("ein") or ""
    for key, val in (mapped.get("wages") or {}).items():
        if doc["wages"].get(key) in (None, 0, 0.0, "") and val not in (None, 0, 0.0, ""):
            doc["wages"][key] = val
    for key, val in (mapped.get("state") or {}).items():
        if doc["state"].get(key) in (None, 0, 0.0, "") and val not in (None, 0, 0.0, ""):
            doc["state"][key] = val
    if (doc.get("tax_year") in (None, 0, "")) and mapped.get("tax_year"):
        doc["tax_year"] = mapped["tax_year"]
    # If form provided numeric wages, treat as high confidence.
    if any(v > 0 for v in (mapped.get("wages") or {}).values()):
        doc["ocr_quality"] = 1.0


def _merge_docs(primary: Dict[str, Any], secondary: Dict[str, Any]) -> Dict[str, Any]:
    """Fill missing/empty values in primary with values from secondary."""
    merged = primary
    for section in ("employee", "employer", "wages", "state"):
        if section not in merged or not isinstance(merged[section], dict):
            merged[section] = {}
        if section in secondary and isinstance(secondary[section], dict):
            for key, val in secondary[section].items():
                current = merged[section].get(key)
                if (current in ("", None) or safe_float(current, 0.0) == 0.0) and val not in ("", None):
                    merged[section][key] = val
    if merged.get("tax_year") in (None, "", 0) and secondary.get("tax_year"):
        merged["tax_year"] = secondary["tax_year"]
    return merged


def _merge_1099int(primary: Dict[str, Any], secondary: Dict[str, Any]) -> Dict[str, Any]:
    merged = primary
    for section in ("payer", "recipient", "filer", "student", "transferor", "creditor", "debtor", "trustee", "participant"):
        if section not in merged or not isinstance(merged[section], dict):
            merged[section] = {}
        if section in secondary and isinstance(secondary[section], dict):
            for key, val in secondary[section].items():
                current = merged[section].get(key)
                if (current in ("", None) or safe_float(current, 0.0) == 0.0) and val not in ("", None):
                    merged[section][key] = val
    if "amounts" in secondary and isinstance(secondary["amounts"], dict):
        merged.setdefault("amounts", {})
        for key, val in secondary["amounts"].items():
            current = merged["amounts"].get(key)
            if (current in ("", None) or safe_float(current, 0.0) == 0.0) and val not in ("", None):
                merged["amounts"][key] = val
    if "flags" in secondary and isinstance(secondary["flags"], dict):
        merged.setdefault("flags", {})
        for key, val in secondary["flags"].items():
            current = merged["flags"].get(key)
            if current in (None, "") and val is not None:
                merged["flags"][key] = val
    for key in (
        "box3_distribution_code",
        "box4_trustee_to_trustee_transfer",
        "box5_qualified_tuition_program",
        "box6_life_insurance_distributed",
        "qualified_tuition_program_529",
        "coverdell_esa",
    ):
        if key in secondary and merged.get(key) in ("", None, False):
            merged[key] = secondary[key]
    if merged.get("tax_year") in (None, "", 0) and secondary.get("tax_year"):
        merged["tax_year"] = secondary["tax_year"]
    return merged


def _extract_1099int_boxes_from_text(text: str) -> Dict[str, float]:
    """Extract numeric 1099-INT box values from text."""
    labels = {
        "box_1_interest_income": ["1", "interest income"],
        "box_2_early_withdrawal_penalty": ["2", "early withdrawal penalty"],
        "box_3_us_savings_bonds_and_treasury_interest": ["3", "u.s. savings bonds", "treasury interest"],
        "box_4_federal_income_tax_withheld": ["4", "federal income tax withheld"],
        "box_5_investment_expenses": ["5", "investment expenses"],
        "box_6_foreign_tax_paid": ["6", "foreign tax paid"],
        "box_8_tax_exempt_interest": ["8", "tax-exempt interest"],
        "box_9_specified_private_activity_bond_interest": ["9", "specified private activity bond interest"],
        "box_10_market_discount": ["10", "market discount"],
        "box_11_bond_premium": ["11", "bond premium"],
    }
    results: Dict[str, float] = {}
    for key, patterns in labels.items():
        val = 0.0
        for p in patterns:
            pattern = rf"{re.escape(p)}[\s:]*\$?([\d,]+(?:\.\d+)?)"
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                val = safe_float(match.group(1), 0.0)
                break
        if val <= 0:
            # Try box number at line start
            box_num = patterns[0]
            pattern = rf"^{re.escape(box_num)}\s+[A-Za-z, /&]+?\s+\$?([\d,]+(?:\.\d+)?)"
            match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
            if match:
                val = safe_float(match.group(1), 0.0)
        if val > 0:
            results[key] = val
    return results


def parse_1099int_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    doc = _blank_1099int(doc_id)
    upper = text.upper()
    payer_tin_match = re.search(r"PAYER['`]?S?\s+TIN[:\s]*([0-9]{2}-?[0-9]{7})", upper, flags=re.IGNORECASE)
    recipient_tin_match = re.search(r"RECIPIENT['`]?S?\s+TIN[:\s]*([0-9]{3}-?[0-9]{2}-?[0-9]{4})", upper, flags=re.IGNORECASE)
    if payer_tin_match:
        doc["payer"]["tin"] = payer_tin_match.group(1)
    if recipient_tin_match:
        doc["recipient"]["tin"] = recipient_tin_match.group(1)
    year_match = re.search(r"\b(20\d{2}|2010)\b", text)
    if year_match:
        try:
            doc["tax_year"] = int(year_match.group(1))
        except Exception:
            doc["tax_year"] = None
    doc["amounts"].update(_extract_1099int_boxes_from_text(text))
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc

def map_1099g_fields_from_form(form_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Map common 1099-G form fields to our normalized structure."""

    def get_first(*keys: str, default: str | None = None) -> str | None:
        for k in keys:
            if k in form_fields and str(form_fields[k]).strip():
                return str(form_fields[k]).strip()
        return default

    def parse_float(val: Any) -> float:
        return safe_float(val, 0.0)

    payer_tin = get_first("PAYER_TIN", "FILER_TIN", "PayerTIN", "f1_1")
    recipient_tin = get_first("RECIPIENT_TIN", "RecipientTIN", "f1_8")
    tax_year = get_first("TaxYear", "Year", "f1_11")
    try:
        tax_year_int = int(tax_year) if tax_year else None
    except Exception:
        tax_year_int = None

    return {
        "tax_year": tax_year_int,
        "payer": {"tin": payer_tin},
        "recipient": {"tin": recipient_tin},
        "amounts": {
            "box1_unemployment_compensation": parse_float(get_first("Box1", "UnemploymentCompensation")),
            "box2_state_local_tax_refunds": parse_float(get_first("Box2", "StateTaxRefunds")),
            "box4_federal_income_tax_withheld": parse_float(get_first("Box4", "FederalTaxWithheld")),
            "box5_rtaa_payments": parse_float(get_first("Box5", "RTAA")),
            "box6_taxable_grants": parse_float(get_first("Box6", "TaxableGrants")),
            "box7_agricultural_payments": parse_float(get_first("Box7", "AgriculturalPayments")),
            "box9_market_gain": parse_float(get_first("Box9", "MarketGain")),
        },
        "box3_box2_tax_year": tax_year_int,
    }

def map_1099s_fields_from_form(form_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Map common 1099-S form fields to our normalized structure."""

    def get_first(*keys: str, default: str | None = None) -> str | None:
        for k in keys:
            if k in form_fields and str(form_fields[k]).strip():
                return str(form_fields[k]).strip()
        return default

    def parse_float(val: Any) -> float:
        return safe_float(val, 0.0)

    filer_tin = get_first("PAYER_TIN", "FILER_TIN", "PayerTIN", "f1_1")
    transferor_tin = get_first("RECIPIENT_TIN", "TRANSFEROR_TIN", "f1_8")
    tax_year = get_first("TaxYear", "Year", "f1_11")
    try:
        tax_year_int = int(tax_year) if tax_year else None
    except Exception:
        tax_year_int = None

    return {
        "tax_year": tax_year_int,
        "filer": {"tin": filer_tin},
        "transferor": {"tin": transferor_tin},
        "amounts": {
            "box1_gross_proceeds": parse_float(get_first("Box1", "GrossProceeds")),
            "box4_federal_income_tax_withheld": parse_float(get_first("Box4", "FederalTaxWithheld")),
        },
    }

def map_1099c_fields_from_form(form_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Map common 1099-C form fields to our normalized structure."""

    def get_first(*keys: str, default: str | None = None) -> str | None:
        for k in keys:
            if k in form_fields and str(form_fields[k]).strip():
                return str(form_fields[k]).strip()
        return default

    def parse_float(val: Any) -> float:
        return safe_float(val, 0.0)

    creditor_tin = get_first("CREDITOR_TIN", "PayerTIN", "f1_1")
    debtor_tin = get_first("DEBTOR_TIN", "RecipientTIN", "f1_8")
    tax_year = get_first("TaxYear", "Year", "f1_11")
    try:
        tax_year_int = int(tax_year) if tax_year else None
    except Exception:
        tax_year_int = None

    return {
        "tax_year": tax_year_int,
        "creditor": {"tin": creditor_tin},
        "debtor": {"tin": debtor_tin},
        "amounts": {
            "box2_amount_of_debt_discharged": parse_float(get_first("Box2", "DebtDischarged")),
            "box3_interest_if_included": parse_float(get_first("Box3", "InterestIncluded")),
            "box7_fair_market_value_property": parse_float(get_first("Box7", "FMVProperty")),
        },
        "box1_date_of_identifiable_event": get_first("Box1", "EventDate", default=""),
        "box6_identifiable_event_code": get_first("Box6", "EventCode", default=""),
    }

def map_1099sa_fields_from_form(form_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Map common 1099-SA form fields to our normalized structure."""

    def get_first(*keys: str, default: str | None = None) -> str | None:
        for k in keys:
            if k in form_fields and str(form_fields[k]).strip():
                return str(form_fields[k]).strip()
        return default

    def parse_float(val: Any) -> float:
        return safe_float(val, 0.0)

    payer_tin = get_first("PAYER_TIN", "FILER_TIN", "PayerTIN", "f1_1")
    recipient_tin = get_first("RECIPIENT_TIN", "RecipientTIN", "f1_8")
    tax_year = get_first("TaxYear", "Year", "f1_11")
    try:
        tax_year_int = int(tax_year) if tax_year else None
    except Exception:
        tax_year_int = None

    return {
        "tax_year": tax_year_int,
        "payer": {"tin": payer_tin},
        "recipient": {"tin": recipient_tin},
        "amounts": {
            "box1_gross_distribution": parse_float(get_first("Box1", "GrossDistribution")),
            "box2_earnings_on_excess_contributions": parse_float(get_first("Box2", "EarningsOnExcess")),
            "box4_federal_income_tax_withheld": parse_float(get_first("Box4", "FederalTaxWithheld")),
            "box5_fair_market_value_hsa_msa": parse_float(get_first("Box5", "FMV")),
        },
        "box3_distribution_code": get_first("Box3", "DistributionCode", default=""),
    }

def map_5498_fields_from_form(form_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Map common 5498 form fields to our normalized structure."""

    def get_first(*keys: str, default: str | None = None) -> str | None:
        for k in keys:
            if k in form_fields and str(form_fields[k]).strip():
                return str(form_fields[k]).strip()
        return default

    def parse_float(val: Any) -> float:
        return safe_float(val, 0.0)

    trustee_tin = get_first("PAYER_TIN", "TRUSTEE_TIN", "PayerTIN", "f1_1")
    participant_tin = get_first("RECIPIENT_TIN", "PARTICIPANT_TIN", "RecipientTIN", "f1_8")
    tax_year = get_first("TaxYear", "Year", "f1_11")
    try:
        tax_year_int = int(tax_year) if tax_year else None
    except Exception:
        tax_year_int = None

    return {
        "tax_year": tax_year_int,
        "trustee": {"tin": trustee_tin},
        "participant": {"tin": participant_tin},
        "amounts": {
            "box1_ira_contributions": parse_float(get_first("Box1", "IRAContributions")),
            "box2_rollover_contributions": parse_float(get_first("Box2", "RolloverContributions")),
            "box3_roth_ira_conversion_amount": parse_float(get_first("Box3", "RothConversions")),
            "box4_recharacterized_contributions": parse_float(get_first("Box4", "RecharacterizedContributions")),
            "box5_fmv_of_account": parse_float(get_first("Box5", "FMV")),
            "box7_roth_ira_contributions": parse_float(get_first("Box7", "RothContributions")),
            "box8_sep_contributions": parse_float(get_first("Box8", "SEPContributions")),
            "box9_simple_contributions": parse_float(get_first("Box9", "SIMPLEContributions")),
            "box13_rmd_amount": parse_float(get_first("Box13", "RMDAmount")),
            "box14_hsa_msa_contributions": parse_float(get_first("Box14", "HSAContributions")),
            "box15_other_contributions": parse_float(get_first("Box15", "OtherContributions")),
        },
        "flags": {},
    }

def map_1099q_fields_from_form(form_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Map common 1099-Q form fields to our normalized structure."""

    def get_first(*keys: str, default: str | None = None) -> str | None:
        for k in keys:
            if k in form_fields and str(form_fields[k]).strip():
                return str(form_fields[k]).strip()
        return default

    def parse_float(val: Any) -> float:
        return safe_float(val, 0.0)

    payer_tin = get_first("PAYER_TIN", "PayerTIN", "f1_1")
    recipient_tin = get_first("RECIPIENT_TIN", "RecipientTIN", "f1_8")
    tax_year = get_first("TaxYear", "Year", "f1_11")
    try:
        tax_year_int = int(tax_year) if tax_year else None
    except Exception:
        tax_year_int = None

    return {
        "tax_year": tax_year_int,
        "payer": {"tin": payer_tin},
        "recipient": {"tin": recipient_tin},
        "amounts": {
            "box1_gross_distribution": parse_float(get_first("Box1", "GrossDistribution")),
            "box2_earnings": parse_float(get_first("Box2", "Earnings")),
            "box3_basis": parse_float(get_first("Box3", "Basis")),
        },
    }


def parse_1099nec_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    doc = _blank_1099nec(doc_id)
    upper = text.upper()
    payer_tin_match = re.search(r"PAYER['`]?S?\s+TIN[:\s]*([0-9]{2}-?[0-9]{7})", upper, flags=re.IGNORECASE)
    recipient_tin_match = re.search(r"RECIPIENT['`]?S?\s+TIN[:\s]*([0-9]{3}-?[0-9]{2}-?[0-9]{4})", upper, flags=re.IGNORECASE)
    if payer_tin_match:
        doc["payer"]["tin"] = payer_tin_match.group(1)
    if recipient_tin_match:
        doc["recipient"]["tin"] = recipient_tin_match.group(1)
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        try:
            doc["tax_year"] = int(year_match.group(1))
        except Exception:
            doc["tax_year"] = None
    # extract compensation and withholding
    comp_match = re.search(r"BOX\s*1[^0-9]*\$?([\d,]+(?:\.\d+)?)", upper)
    if comp_match:
        doc["amounts"]["box_1_nonemployee_compensation"] = safe_float(comp_match.group(1), 0.0)
    wh_match = re.search(r"BOX\s*4[^0-9]*\$?([\d,]+(?:\.\d+)?)", upper)
    if wh_match:
        doc["amounts"]["box_4_federal_income_tax_withheld"] = safe_float(wh_match.group(1), 0.0)
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc

def parse_1099misc_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    doc = _blank_1099misc(doc_id)
    upper = text.upper()
    payer_tin_match = re.search(r"PAYER['`]?S?\s+TIN[:\s]*([0-9]{2}-?[0-9]{7})", upper, flags=re.IGNORECASE)
    recipient_tin_match = re.search(r"RECIPIENT['`]?S?\s+TIN[:\s]*([0-9]{3}-?[0-9]{2}-?[0-9]{4})", upper, flags=re.IGNORECASE)
    if payer_tin_match:
        doc["payer"]["tin"] = payer_tin_match.group(1)
    if recipient_tin_match:
        doc["recipient"]["tin"] = recipient_tin_match.group(1)
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        try:
            doc["tax_year"] = int(year_match.group(1))
        except Exception:
            doc["tax_year"] = None
    mappings = {
        "box_1_rents": r"BOX\s*1[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_2_royalties": r"BOX\s*2[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_3_other_income": r"BOX\s*3[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_4_federal_income_tax_withheld": r"BOX\s*4[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_6_medical_healthcare_payments": r"BOX\s*6[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_10_gross_proceeds_paid_to_attorney": r"BOX\s*10[^0-9]*\$?([\d,]+(?:\.\d+)?)",
    }
    for key, pattern in mappings.items():
        match = re.search(pattern, upper)
        if match:
            doc["amounts"][key] = safe_float(match.group(1), 0.0)
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc

def parse_1099div_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    doc = _blank_1099div(doc_id)
    upper = text.upper()
    payer_tin_match = re.search(r"PAYER['`]?S?\s+TIN[:\s]*([0-9]{2}-?[0-9]{7})", upper, flags=re.IGNORECASE)
    recipient_tin_match = re.search(r"RECIPIENT['`]?S?\s+TIN[:\s]*([0-9]{3}-?[0-9]{2}-?[0-9]{4})", upper, flags=re.IGNORECASE)
    if payer_tin_match:
        doc["payer"]["tin"] = payer_tin_match.group(1)
    if recipient_tin_match:
        doc["recipient"]["tin"] = recipient_tin_match.group(1)
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        try:
            doc["tax_year"] = int(year_match.group(1))
        except Exception:
            doc["tax_year"] = None
    mappings = {
        "box_1a_total_ordinary_dividends": r"BOX\s*1A[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_1b_qualified_dividends": r"BOX\s*1B[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_2a_total_capital_gain_distributions": r"BOX\s*2A[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_4_federal_income_tax_withheld": r"BOX\s*4[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_6_foreign_tax_paid": r"BOX\s*6[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_11_section_199a_dividends": r"BOX\s*11[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_12_exempt_interest_dividends": r"BOX\s*12[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_13_specified_private_activity_bond_interest_dividends": r"BOX\s*13[^0-9]*\$?([\d,]+(?:\.\d+)?)",
    }
    for key, pattern in mappings.items():
        match = re.search(pattern, upper)
        if match:
            doc["amounts"][key] = safe_float(match.group(1), 0.0)
    country_match = re.search(r"BOX\s*7[^A-Z]*([A-Z][A-Z\s]+)", upper)
    if country_match:
        doc["box_7_foreign_country_or_possession"] = country_match.group(1).title().strip()
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc

def parse_1099k_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    doc = _blank_1099k(doc_id)
    upper = text.upper()
    payer_tin_match = re.search(r"PAYER['`]?S?\s+TIN[:\s]*([0-9]{2}-?[0-9]{7})", upper, flags=re.IGNORECASE)
    recipient_tin_match = re.search(r"PAYEE['`]?S?\s+TIN[:\s]*([0-9]{3}-?[0-9]{2}-?[0-9]{4})", upper, flags=re.IGNORECASE)
    if payer_tin_match:
        doc["payer"]["tin"] = payer_tin_match.group(1)
    if recipient_tin_match:
        doc["recipient"]["tin"] = recipient_tin_match.group(1)
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        try:
            doc["tax_year"] = int(year_match.group(1))
        except Exception:
            doc["tax_year"] = None
    patterns = {
        "box_1a_gross_amount": r"BOX\s*1A[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_1b_card_not_present": r"BOX\s*1B[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_3_number_of_payment_transactions": r"BOX\s*3[^0-9]*([\d,]+(?:\.\d+)?)",
        "box_4_federal_income_tax_withheld": r"BOX\s*4[^0-9]*\$?([\d,]+(?:\.\d+)?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, upper)
        if match:
            doc["amounts"][key] = safe_float(match.group(1), 0.0)
    mcc_match = re.search(r"MCC[:\s]+([0-9A-Z]{3,4})", upper)
    if mcc_match:
        doc["box_2_merchant_category_code"] = mcc_match.group(1)
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc

def parse_1099r_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    doc = _blank_1099r(doc_id)
    upper = text.upper()
    payer_tin_match = re.search(r"PAYER['`]?S?\s+TIN[:\s]*([0-9]{2}-?[0-9]{7})", upper, flags=re.IGNORECASE)
    recipient_tin_match = re.search(r"RECIPIENT['`]?S?\s+TIN[:\s]*([0-9]{3}-?[0-9]{2}-?[0-9]{4})", upper, flags=re.IGNORECASE)
    if payer_tin_match:
        doc["payer"]["tin"] = payer_tin_match.group(1)
    if recipient_tin_match:
        doc["recipient"]["tin"] = recipient_tin_match.group(1)
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        try:
            doc["tax_year"] = int(year_match.group(1))
        except Exception:
            doc["tax_year"] = None
    patterns = {
        "box_1_gross_distribution": r"BOX\s*1[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_2a_taxable_amount": r"BOX\s*2A[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_3_capital_gain_included": r"BOX\s*3[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_4_federal_income_tax_withheld": r"BOX\s*4[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_5_employee_contributions_or_insurance_premiums": r"BOX\s*5[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_9b_total_employee_contributions": r"BOX\s*9B[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_10_amount_allocable_to_IRR": r"BOX\s*10[^0-9]*\$?([\d,]+(?:\.\d+)?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, upper)
        if match:
            doc["amounts"][key] = safe_float(match.group(1), 0.0)
    codes_match = re.search(r"BOX\s*7[^A-Z0-9]*([A-Z0-9 ,/]+)", upper)
    if codes_match:
        raw = codes_match.group(1)
        codes = [c.strip() for c in re.split(r"[ ,/]+", raw) if c.strip()]
        doc["box_7_distribution_codes"] = codes
    if "IRA" in upper or "SEP" in upper or "SIMPLE" in upper:
        doc["box_7_ira_sep_simple_indicator"] = True
    if "TAXABLE AMOUNT NOT DETERMINED" in upper:
        doc["box_2b_taxable_amount_not_determined"] = True
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc

def parse_1099g_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    doc = _blank_1099g(doc_id)
    upper = text.upper()
    payer_tin_match = re.search(r"PAYER['`]?S?\s+TIN[:\s]*([0-9]{2}-?[0-9]{7})", upper, flags=re.IGNORECASE)
    recipient_tin_match = re.search(r"RECIPIENT['`]?S?\s+TIN[:\s]*([0-9]{3}-?[0-9]{2}-?[0-9]{4})", upper, flags=re.IGNORECASE)
    if payer_tin_match:
        doc["payer"]["tin"] = payer_tin_match.group(1)
    if recipient_tin_match:
        doc["recipient"]["tin"] = recipient_tin_match.group(1)
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        try:
            doc["tax_year"] = int(year_match.group(1))
        except Exception:
            doc["tax_year"] = None
    patterns = {
        "box1_unemployment_compensation": r"BOX\s*1[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box2_state_local_tax_refunds": r"BOX\s*2[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box4_federal_income_tax_withheld": r"BOX\s*4[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box5_rtaa_payments": r"BOX\s*5[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box6_taxable_grants": r"BOX\s*6[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box7_agricultural_payments": r"BOX\s*7[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box9_market_gain": r"BOX\s*9[^0-9]*\$?([\d,]+(?:\.\d+)?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, upper)
        if match:
            doc["amounts"][key] = safe_float(match.group(1), 0.0)
    tax_year_box3 = re.search(r"BOX\s*3[^0-9]*(20\d{2})", upper)
    if tax_year_box3:
        try:
            doc["box3_box2_tax_year"] = int(tax_year_box3.group(1))
        except Exception:
            doc["box3_box2_tax_year"] = None
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc

def parse_1099s_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    doc = _blank_1099s(doc_id)
    upper = text.upper()
    filer_tin_match = re.search(r"PAYER['`]?S?\s+TIN[:\s]*([0-9]{2}-?[0-9]{7})", upper, flags=re.IGNORECASE)
    transferor_tin_match = re.search(r"TRANSFEROR['`]?S?\s+TIN[:\s]*([0-9]{3}-?[0-9]{2}-?[0-9]{4})", upper, flags=re.IGNORECASE)
    if filer_tin_match:
        doc["filer"]["tin"] = filer_tin_match.group(1)
    if transferor_tin_match:
        doc["transferor"]["tin"] = transferor_tin_match.group(1)
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        try:
            doc["tax_year"] = int(year_match.group(1))
        except Exception:
            doc["tax_year"] = None
    patterns = {
        "box1_gross_proceeds": r"BOX\s*1[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box4_federal_income_tax_withheld": r"BOX\s*4[^0-9]*\$?([\d,]+(?:\.\d+)?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, upper)
        if match:
            doc["amounts"][key] = safe_float(match.group(1), 0.0)
    closing_match = re.search(r"CLOSING\s*DATE[:\s]*([0-9]{4}-[0-9]{2}-[0-9]{2})", text, flags=re.IGNORECASE)
    if closing_match:
        doc["closing_date"] = closing_match.group(1)
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc

def parse_1099c_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    doc = _blank_1099c(doc_id)
    upper = text.upper()
    creditor_tin_match = re.search(r"CREDITOR['`]?S?\s+TIN[:\s]*([0-9]{2}-?[0-9]{7})", upper, flags=re.IGNORECASE)
    debtor_tin_match = re.search(r"DEBTOR['`]?S?\s+TIN[:\s]*([0-9]{3}-?[0-9]{2}-?[0-9]{4})", upper, flags=re.IGNORECASE)
    if creditor_tin_match:
        doc["creditor"]["tin"] = creditor_tin_match.group(1)
    if debtor_tin_match:
        doc["debtor"]["tin"] = debtor_tin_match.group(1)
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        try:
            doc["tax_year"] = int(year_match.group(1))
        except Exception:
            doc["tax_year"] = None
    patterns = {
        "box2_amount_of_debt_discharged": r"BOX\s*2[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box3_interest_if_included": r"BOX\s*3[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box7_fair_market_value_property": r"BOX\s*7[^0-9]*\$?([\d,]+(?:\.\d+)?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, upper)
        if match:
            doc["amounts"][key] = safe_float(match.group(1), 0.0)
    event_code_match = re.search(r"BOX\s*6[^A-Z0-9]*([A-Z0-9]+)", upper)
    if event_code_match:
        doc["box6_identifiable_event_code"] = event_code_match.group(1)
    date_match = re.search(r"BOX\s*1[^0-9]*(\d{4}-\d{2}-\d{2})", text)
    if date_match:
        doc["box1_date_of_identifiable_event"] = date_match.group(1)
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc

def parse_1099sa_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    doc = _blank_1099sa(doc_id)
    upper = text.upper()
    payer_tin_match = re.search(r"PAYER['`]?S?\s+TIN[:\s]*([0-9]{2}-?[0-9]{7})", upper, flags=re.IGNORECASE)
    recipient_tin_match = re.search(r"RECIPIENT['`]?S?\s+TIN[:\s]*([0-9]{3}-?[0-9]{2}-?[0-9]{4})", upper, flags=re.IGNORECASE)
    if payer_tin_match:
        doc["payer"]["tin"] = payer_tin_match.group(1)
    if recipient_tin_match:
        doc["recipient"]["tin"] = recipient_tin_match.group(1)
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        try:
            doc["tax_year"] = int(year_match.group(1))
        except Exception:
            doc["tax_year"] = None
    patterns = {
        "box1_gross_distribution": r"BOX\s*1[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box2_earnings_on_excess_contributions": r"BOX\s*2[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box4_federal_income_tax_withheld": r"BOX\s*4[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box5_fair_market_value_hsa_msa": r"BOX\s*5[^0-9]*\$?([\d,]+(?:\.\d+)?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, upper)
        if match:
            doc["amounts"][key] = safe_float(match.group(1), 0.0)
    code_match = re.search(r"BOX\s*3[^A-Z0-9]*([A-Z0-9]+)", upper)
    if code_match:
        doc["box3_distribution_code"] = code_match.group(1)
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc

def parse_5498_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    doc = _blank_5498(doc_id)
    upper = text.upper()
    trustee_tin_match = re.search(r"(PAYER|TRUSTEE)['`]?S?\s+TIN[:\s]*([0-9]{2}-?[0-9]{7})", upper, flags=re.IGNORECASE)
    participant_tin_match = re.search(r"(PARTICIPANT|RECIPIENT)['`]?S?\s+TIN[:\s]*([0-9]{3}-?[0-9]{2}-?[0-9]{4})", upper, flags=re.IGNORECASE)
    if trustee_tin_match:
        doc["trustee"]["tin"] = trustee_tin_match.group(2)
    if participant_tin_match:
        doc["participant"]["tin"] = participant_tin_match.group(2)
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        try:
            doc["tax_year"] = int(year_match.group(1))
        except Exception:
            doc["tax_year"] = None
    patterns = {
        "box1_ira_contributions": r"BOX\s*1[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box2_rollover_contributions": r"BOX\s*2[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box3_roth_ira_conversion_amount": r"BOX\s*3[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box4_recharacterized_contributions": r"BOX\s*4[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box5_fmv_of_account": r"BOX\s*5[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box7_roth_ira_contributions": r"BOX\s*7[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box8_sep_contributions": r"BOX\s*8[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box9_simple_contributions": r"BOX\s*9[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box13_rmd_amount": r"BOX\s*13[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box14_hsa_msa_contributions": r"BOX\s*14[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box15_other_contributions": r"BOX\s*15[^0-9]*\$?([\d,]+(?:\.\d+)?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, upper)
        if match:
            doc["amounts"][key] = safe_float(match.group(1), 0.0)
    if "REQUIRED MINIMUM DISTRIBUTION" in upper:
        doc["box11_required_minimum_distribution_indicator"] = True
    rmd_date_match = re.search(r"RMD\s*DATE[:\s]*([0-9]{4}-[0-9]{2}-[0-9]{2})", text, flags=re.IGNORECASE)
    if rmd_date_match:
        doc["box12_rmd_date"] = rmd_date_match.group(1)
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc

def parse_1099q_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    doc = _blank_1099q(doc_id)
    upper = text.upper()
    payer_tin_match = re.search(r"PAYER['`]?S?\s+TIN[:\s]*([0-9]{2}-?[0-9]{7})", upper, flags=re.IGNORECASE)
    recipient_tin_match = re.search(r"RECIPIENT['`]?S?\s+TIN[:\s]*([0-9]{3}-?[0-9]{2}-?[0-9]{4})", upper, flags=re.IGNORECASE)
    if payer_tin_match:
        doc["payer"]["tin"] = payer_tin_match.group(1)
    if recipient_tin_match:
        doc["recipient"]["tin"] = recipient_tin_match.group(1)
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        try:
            doc["tax_year"] = int(year_match.group(1))
        except Exception:
            doc["tax_year"] = None
    patterns = {
        "box1_gross_distribution": r"BOX\s*1[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box2_earnings": r"BOX\s*2[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box3_basis": r"BOX\s*3[^0-9]*\$?([\d,]+(?:\.\d+)?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, upper)
        if match:
            doc["amounts"][key] = safe_float(match.group(1), 0.0)
    if "TRUSTEE-TO-TRUSTEE" in upper:
        doc["box4_trustee_to_trustee_transfer"] = True
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc

def parse_1098_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    doc = _blank_1098(doc_id)
    upper = text.upper()
    lender_tin = re.search(r"LENDER['`]?S?\s+TIN[:\s]*([0-9]{2}-?[0-9]{7})", upper, flags=re.IGNORECASE)
    borrower_tin = re.search(r"BORROWER['`]?S?\s+TIN[:\s]*([0-9]{3}-?[0-9]{2}-?[0-9]{4})", upper, flags=re.IGNORECASE)
    if lender_tin:
        doc["payer"]["tin"] = lender_tin.group(1)
    if borrower_tin:
        doc["recipient"]["tin"] = borrower_tin.group(1)
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        try:
            doc["tax_year"] = int(year_match.group(1))
        except Exception:
            doc["tax_year"] = None
    patterns = {
        "box_1_mortgage_interest_received": r"BOX\s*1[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_2_outstanding_mortgage_principal": r"BOX\s*2[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_4_refunded_interest": r"BOX\s*4[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_5_mortgage_insurance_premiums": r"BOX\s*5[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_6_points_paid_on_purchase": r"BOX\s*6[^0-9]*\$?([\d,]+(?:\.\d+)?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, upper)
        if match:
            doc["amounts"][key] = safe_float(match.group(1), 0.0)
    orig_date = re.search(r"BOX\s*3[^0-9A-Z]*([0-9/\\-]+)", upper)
    if orig_date:
        doc["box_3_mortgage_origination_date"] = orig_date.group(1).strip()
    addr_match = re.search(r"PROPERTY\s+ADDRESS[:\\s]*(.+)", text, flags=re.IGNORECASE)
    if addr_match:
        doc["box_7_mortgaged_property_address"] = addr_match.group(1).strip()
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc

def parse_1095a_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    doc = _blank_1095a(doc_id)
    upper = text.upper()
    recipient_tin = re.search(r"RECIPIENT['`]?S?\s+TIN[:\s]*([0-9]{3}-?[0-9]{2}-?[0-9]{4})", upper, flags=re.IGNORECASE)
    if recipient_tin:
        doc["recipient"]["tin"] = recipient_tin.group(1)
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        try:
            doc["tax_year"] = int(year_match.group(1))
        except Exception:
            doc["tax_year"] = None
    months = []
    for idx in range(1, 13):
        # Look for patterns like "Jan" or "1" near columns A/B/C
        months.append(
            {
                "month_index": idx,
                "monthly_premium": 0.0,
                "slcsp_premium": 0.0,
                "advance_premium_tax_credit": 0.0,
            }
        )
    doc["months"] = months
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc

def parse_941_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    doc = _blank_941(doc_id)
    upper = text.upper()
    ein_match = re.search(r"\bEIN[:\s]*([0-9]{2}-?[0-9]{7})", upper)
    if ein_match:
        doc["employer"]["ein"] = ein_match.group(1)
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        try:
            doc["tax_year"] = int(year_match.group(1))
        except Exception:
            doc["tax_year"] = None
    quarter_match = re.search(r"QUARTER\s*([1-4])", upper)
    if quarter_match:
        try:
            doc["tax_quarter"] = int(quarter_match.group(1))
        except Exception:
            doc["tax_quarter"] = None
    patterns = {
        "line_1_num_employees": r"LINE\s*1[^0-9]*([\d,]+)",
        "line_2_wages_tips_other_comp": r"LINE\s*2[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "line_3_income_tax_withheld": r"LINE\s*3[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "line_5a_taxable_ss_wages": r"LINE\s*5A[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "line_5a_ss_tax": r"LINE\s*5A[^0-9A-Z]*TAX[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "line_5b_taxable_ss_tips": r"LINE\s*5B[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "line_5b_ss_tax_tips": r"LINE\s*5B[^0-9A-Z]*TAX[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "line_5c_taxable_medicare_wages": r"LINE\s*5C[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "line_5c_medicare_tax": r"LINE\s*5C[^0-9A-Z]*TAX[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "line_5d_taxable_addl_medicare_wages": r"LINE\s*5D[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "line_5d_addl_medicare_tax": r"LINE\s*5D[^0-9A-Z]*TAX[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "line_6_total_taxes_before_adjustments": r"LINE\s*6[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "line_7_current_quarter_fractions_of_cents_adjustment": r"LINE\s*7[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "line_8_tip_adjustment": r"LINE\s*8[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "line_9_sick_pay_adjustment": r"LINE\s*9[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "line_10_total_taxes_after_adjustments": r"LINE\s*10[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "line_11_total_deposits_for_quarter": r"LINE\s*11[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "line_12_refundable_credits": r"LINE\s*12[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "line_13_total_taxes_after_credits": r"LINE\s*13[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "line_14_balance_due": r"LINE\s*14[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "line_15_overpayment": r"LINE\s*15[^0-9]*\$?([\d,]+(?:\.\d+)?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, upper)
        if match:
            doc["amounts"][key] = safe_float(match.group(1), 0.0)
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc

def parse_w9_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    doc = _blank_w9(doc_id)
    upper = text.upper()
    tin_match = re.search(r"\b([0-9]{3}-[0-9]{2}-[0-9]{4})\b", upper)
    ein_match = re.search(r"\b([0-9]{2}-[0-9]{7})\b", upper)
    if tin_match:
        doc["ssn"] = tin_match.group(1)
        doc["tin_raw"] = tin_match.group(1)
    if ein_match:
        doc["ein"] = ein_match.group(1)
        doc["tin_raw"] = ein_match.group(1)
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        try:
            doc["tax_year"] = int(year_match.group(1))
        except Exception:
            doc["tax_year"] = None
    name_match = re.search(r"NAME[:\s]*([A-Z ,.'-]+)", upper)
    if name_match:
        doc["taxpayer_name"] = name_match.group(1).title()
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc

def _blank_1099b(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_type": "1099-B",
        "tax_year": None,
        "broker": {"name": "", "tin": "", "address": ""},
        "recipient": {"name": "", "tin": "", "address": ""},
        "transactions": [],
        "ocr_quality": 1.0,
    }

def _blank_1098t(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_type": "1098-T",
        "tax_year": None,
        "filer": {"name": "", "tin": "", "address": ""},
        "student": {"name": "", "tin": "", "address": ""},
        "account_number": "",
        "amounts": {
            "box1_payments_received": 0.0,
            "box2_amounts_billed": 0.0,
            "box4_adjustments_prior_year": 0.0,
            "box5_scholarships_grants": 0.0,
            "box6_adj_scholarships_prior_year": 0.0,
            "box10_insurance_reimbursements": 0.0,
        },
        "flags": {
            "box3_reporting_method_changed": False,
            "box7_include_jan_mar": False,
            "box8_at_least_half_time": False,
            "box9_graduate_student": False,
        },
        "ocr_quality": 1.0,
    }

def _blank_ssa1099(doc_id: str) -> Dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_type": "SSA-1099",
        "tax_year": None,
        "payer": {"name": "Social Security Administration", "tin": "", "address": ""},
        "beneficiary": {"name": "", "tin": "", "address": ""},
        "amounts": {
            "box_3_benefits_paid": 0.0,
            "box_4_benefits_repaid": 0.0,
            "box_5_net_benefits": 0.0,
            "box_6_voluntary_federal_tax_withheld": 0.0,
            "box_7_medicare_premiums": 0.0,
            "box_8_other_deductions_or_adjustments": 0.0,
            "box_9_state_repayment": 0.0,
        },
        "state_items": [],
        "ocr_quality": 1.0,
    }

def map_1099b_fields_from_form(form_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Map common 1099-B form fields to our normalized structure."""

    def get_first(*keys: str, default: str | None = None) -> str | None:
        for k in keys:
            if k in form_fields and str(form_fields[k]).strip():
                return str(form_fields[k]).strip()
        return default

    def parse_float(val: Any) -> float:
        return safe_float(val, 0.0)

    broker_tin = get_first("BrokerTIN", "PayerTIN", "PAYER_TIN", "f1_1")
    recipient_tin = get_first("RecipientTIN", "RECIPIENT_TIN", "f1_8")
    tax_year = get_first("TaxYear", "Year", "f1_11")
    try:
        tax_year_int = int(tax_year) if tax_year else None
    except Exception:
        tax_year_int = None

    return {
        "tax_year": tax_year_int,
        "broker": {"tin": broker_tin},
        "recipient": {"tin": recipient_tin},
        "transactions": [],
    }

def parse_1099b_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    doc = _blank_1099b(doc_id)
    upper = text.upper()
    broker_tin_match = re.search(r"PAYER['`]?S?\s+TIN[:\s]*([0-9]{2}-?[0-9]{7})", upper, flags=re.IGNORECASE)
    recipient_tin_match = re.search(r"RECIPIENT['`]?S?\s+TIN[:\s]*([0-9]{3}-?[0-9]{2}-?[0-9]{4})", upper, flags=re.IGNORECASE)
    if broker_tin_match:
        doc["broker"]["tin"] = broker_tin_match.group(1)
    if recipient_tin_match:
        doc["recipient"]["tin"] = recipient_tin_match.group(1)
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        try:
            doc["tax_year"] = int(year_match.group(1))
        except Exception:
            doc["tax_year"] = None
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc

def map_1098t_fields_from_form(form_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Map common 1098-T form fields to our normalized structure."""

    def get_first(*keys: str, default: str | None = None) -> str | None:
        for k in keys:
            if k in form_fields and str(form_fields[k]).strip():
                return str(form_fields[k]).strip()
        return default

    def parse_float(val: Any) -> float:
        return safe_float(val, 0.0)

    filer_tin = get_first("PAYER_TIN", "FILER_TIN", "FilerTIN", "f1_1")
    student_tin = get_first("RECIPIENT_TIN", "STUDENT_TIN", "StudentTIN", "f1_8")
    tax_year = get_first("TaxYear", "Year", "f1_11")
    try:
        tax_year_int = int(tax_year) if tax_year else None
    except Exception:
        tax_year_int = None

    return {
        "tax_year": tax_year_int,
        "filer": {"tin": filer_tin},
        "student": {"tin": student_tin},
        "amounts": {
            "box1_payments_received": parse_float(get_first("Box1", "PaymentsReceived")),
            "box2_amounts_billed": parse_float(get_first("Box2", "AmountsBilled")),
            "box4_adjustments_prior_year": parse_float(get_first("Box4", "AdjustmentsPriorYear")),
            "box5_scholarships_grants": parse_float(get_first("Box5", "ScholarshipsGrants")),
            "box6_adj_scholarships_prior_year": parse_float(get_first("Box6", "AdjustmentsScholarshipsPriorYear")),
            "box10_insurance_reimbursements": parse_float(get_first("Box10", "InsuranceReimbursements")),
        },
    }

def parse_1098t_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    doc = _blank_1098t(doc_id)
    upper = text.upper()
    filer_tin_match = re.search(r"PAYER['`]?S?\s+TIN[:\s]*([0-9]{2}-?[0-9]{7})", upper, flags=re.IGNORECASE)
    student_tin_match = re.search(r"STUDENT['`]?S?\s+TIN[:\s]*([0-9]{3}-?[0-9]{2}-?[0-9]{4})", upper, flags=re.IGNORECASE)
    if filer_tin_match:
        doc["filer"]["tin"] = filer_tin_match.group(1)
    if student_tin_match:
        doc["student"]["tin"] = student_tin_match.group(1)
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        try:
            doc["tax_year"] = int(year_match.group(1))
        except Exception:
            doc["tax_year"] = None
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc

def parse_ssa1099_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    doc = _blank_ssa1099(doc_id)
    upper = text.upper()
    tin_match = re.search(r"\b([0-9]{3}-[0-9]{2}-[0-9]{4})\b", upper)
    if tin_match:
        doc["beneficiary"]["tin"] = tin_match.group(1)
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        try:
            doc["tax_year"] = int(year_match.group(1))
        except Exception:
            doc["tax_year"] = None
    patterns = {
        "box_3_benefits_paid": r"BOX\s*3[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_4_benefits_repaid": r"BOX\s*4[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_5_net_benefits": r"BOX\s*5[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_6_voluntary_federal_tax_withheld": r"BOX\s*6[^0-9]*\$?([\d,]+(?:\.\d+)?)",
        "box_7_medicare_premiums": r"BOX\s*7[^0-9]*\$?([\d,]+(?:\.\d+)?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, upper)
        if match:
            doc["amounts"][key] = safe_float(match.group(1), 0.0)
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc


def _normalize_1099int_with_schema(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize through the Int1099Document schema when available."""
    try:
        from schemas.int_1099 import Int1099Document, StateItem
    except Exception:
        return doc

    try:
        payer = doc.get("payer") or {}
        recipient = doc.get("recipient") or {}
        amounts = doc.get("amounts") or {}
        meta = doc.get("meta") or {}
        state_items = [
            item if isinstance(item, StateItem) else StateItem(**item) if isinstance(item, dict) else StateItem()
            for item in doc.get("state_items", [])
        ]
        model = Int1099Document(
            tax_year=doc.get("tax_year"),
            payer_name=payer.get("name", ""),
            payer_tin=payer.get("tin", ""),
            payer_address=payer.get("address", ""),
            recipient_name=recipient.get("name", ""),
            recipient_tin=recipient.get("tin", ""),
            recipient_address=recipient.get("address", ""),
            account_number=doc.get("account_number", ""),
            box_1_interest_income=amounts.get("box_1_interest_income", 0.0),
            box_2_early_withdrawal_penalty=amounts.get("box_2_early_withdrawal_penalty", 0.0),
            box_3_us_savings_bonds_and_treasury_interest=amounts.get("box_3_us_savings_bonds_and_treasury_interest", 0.0),
            box_4_federal_income_tax_withheld=amounts.get("box_4_federal_income_tax_withheld", 0.0),
            box_5_investment_expenses=amounts.get("box_5_investment_expenses", 0.0),
            box_6_foreign_tax_paid=amounts.get("box_6_foreign_tax_paid", 0.0),
            box_7_foreign_country_or_ust_possession=amounts.get("box_7_foreign_country_or_ust_possession", ""),
            box_8_tax_exempt_interest=amounts.get("box_8_tax_exempt_interest", 0.0),
            box_9_specified_private_activity_bond_interest=amounts.get("box_9_specified_private_activity_bond_interest", 0.0),
            box_10_market_discount=amounts.get("box_10_market_discount", 0.0),
            box_11_bond_premium=amounts.get("box_11_bond_premium", 0.0),
            box_12_bond_premium_tax_exempt=amounts.get("box_12_bond_premium_tax_exempt", 0.0),
            box_13_bond_premium_treasury=amounts.get("box_13_bond_premium_treasury", 0.0),
            box_6_foreign_country=doc.get("box_6_foreign_country_or_ust_possession", ""),
            box_14_tax_exempt_cusip=doc.get("box_14_tax_exempt_cusip", ""),
            box_15_state=doc.get("box_15_state", []),
            box_16_state_tax_withheld=doc.get("box_16_state_tax_withheld", []),
            box_17_state_id=doc.get("box_17_state_id", []),
            state_items=state_items,
            ocr_quality=doc.get("ocr_quality"),
            source_pdf_path=meta.get("source_file", ""),
            extraction_engine_version=meta.get("extraction_engine_version", ""),
        )
        normalized = model.to_document_dict()
        normalized["doc_id"] = doc.get("doc_id")
        return normalized
    except Exception:
        return doc


def _normalize_1099nec_with_schema(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize through the Nec1099Document schema when available."""
    try:
        from schemas.nec_1099 import Nec1099Document, StateItem
    except Exception:
        return doc

    try:
        payer = doc.get("payer") or {}
        recipient = doc.get("recipient") or {}
        amounts = doc.get("amounts") or {}
        meta = doc.get("meta") or {}
        state_items = [
            item if isinstance(item, StateItem) else StateItem(**item) if isinstance(item, dict) else StateItem()
            for item in doc.get("state_items", [])
        ]
        model = Nec1099Document(
            tax_year=doc.get("tax_year"),
            payer_name=payer.get("name", ""),
            payer_tin=payer.get("tin", ""),
            payer_address=payer.get("address", ""),
            recipient_name=recipient.get("name", ""),
            recipient_tin=recipient.get("tin", ""),
            recipient_address=recipient.get("address", ""),
            box_1_nonemployee_compensation=amounts.get("box_1_nonemployee_compensation", 0.0),
            box_4_federal_income_tax_withheld=amounts.get("box_4_federal_income_tax_withheld", 0.0),
            box_5_state_tax_withheld_total=amounts.get("box_5_state_tax_withheld_total", 0.0),
            state_items=state_items,
            ocr_quality=doc.get("ocr_quality"),
            source_pdf_path=meta.get("source_file", ""),
            extraction_engine_version=meta.get("extraction_engine_version", ""),
        )
        normalized = model.to_document_dict()
        normalized["doc_id"] = doc.get("doc_id")
        return normalized
    except Exception:
        return doc

def _normalize_1099misc_with_schema(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize through the Misc1099Document schema when available."""
    try:
        from schemas.misc_1099 import Misc1099Document, StateItem
    except Exception:
        return doc

    try:
        payer = doc.get("payer") or {}
        recipient = doc.get("recipient") or {}
        amounts = doc.get("amounts") or {}
        meta = doc.get("meta") or {}
        state_items = [
            item if isinstance(item, StateItem) else StateItem(**item) if isinstance(item, dict) else StateItem()
            for item in doc.get("state_items", [])
        ]
        model = Misc1099Document(
            tax_year=doc.get("tax_year"),
            payer_name=payer.get("name", ""),
            payer_tin=payer.get("tin", ""),
            payer_address=payer.get("address", ""),
            recipient_name=recipient.get("name", ""),
            recipient_tin=recipient.get("tin", ""),
            recipient_address=recipient.get("address", ""),
            box_1_rents=amounts.get("box_1_rents", 0.0),
            box_2_royalties=amounts.get("box_2_royalties", 0.0),
            box_3_other_income=amounts.get("box_3_other_income", 0.0),
            box_4_federal_income_tax_withheld=amounts.get("box_4_federal_income_tax_withheld", 0.0),
            box_6_medical_healthcare_payments=amounts.get("box_6_medical_healthcare_payments", 0.0),
            box_10_gross_proceeds_paid_to_attorney=amounts.get("box_10_gross_proceeds_paid_to_attorney", 0.0),
            state_items=state_items,
            ocr_quality=doc.get("ocr_quality"),
            source_pdf_path=meta.get("source_file", ""),
            extraction_engine_version=meta.get("extraction_engine_version", ""),
        )
        normalized = model.to_document_dict()
        normalized["doc_id"] = doc.get("doc_id")
        return normalized
    except Exception:
        return doc

def _normalize_1099div_with_schema(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize through the Div1099Document schema when available."""
    try:
        from schemas.div_1099 import Div1099Document, StateItem
    except Exception:
        return doc

    try:
        payer = doc.get("payer") or {}
        recipient = doc.get("recipient") or {}
        amounts = doc.get("amounts") or {}
        meta = doc.get("meta") or {}
        state_items = [
            item if isinstance(item, StateItem) else StateItem(**item) if isinstance(item, dict) else StateItem()
            for item in doc.get("state_items", [])
        ]
        model = Div1099Document(
            tax_year=doc.get("tax_year"),
            payer_name=payer.get("name", ""),
            payer_tin=payer.get("tin", ""),
            payer_address=payer.get("address", ""),
            recipient_name=recipient.get("name", ""),
            recipient_tin=recipient.get("tin", ""),
            recipient_address=recipient.get("address", ""),
            box_1a_total_ordinary_dividends=amounts.get("box_1a_total_ordinary_dividends", 0.0),
            box_1b_qualified_dividends=amounts.get("box_1b_qualified_dividends", 0.0),
            box_2a_total_capital_gain_distributions=amounts.get("box_2a_total_capital_gain_distributions", 0.0),
            box_4_federal_income_tax_withheld=amounts.get("box_4_federal_income_tax_withheld", 0.0),
            box_6_foreign_tax_paid=amounts.get("box_6_foreign_tax_paid", 0.0),
            box_7_foreign_country_or_possession=doc.get("box_7_foreign_country_or_possession", ""),
            box_11_section_199a_dividends=amounts.get("box_11_section_199a_dividends", 0.0),
            box_12_exempt_interest_dividends=amounts.get("box_12_exempt_interest_dividends", 0.0),
            box_13_specified_private_activity_bond_interest_dividends=amounts.get("box_13_specified_private_activity_bond_interest_dividends", 0.0),
            state_items=state_items,
            ocr_quality=doc.get("ocr_quality"),
            source_pdf_path=meta.get("source_file", ""),
            extraction_engine_version=meta.get("extraction_engine_version", ""),
        )
        normalized = model.to_document_dict()
        normalized["doc_id"] = doc.get("doc_id")
        return normalized
    except Exception:
        return doc

def _normalize_1099k_with_schema(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize through the K1099Document schema when available."""
    try:
        from schemas.k_1099 import K1099Document, StateItem
    except Exception:
        return doc

    try:
        payer = doc.get("payer") or {}
        recipient = doc.get("recipient") or {}
        amounts = doc.get("amounts") or {}
        meta = doc.get("meta") or {}
        state_items = [
            item if isinstance(item, StateItem) else StateItem(**item) if isinstance(item, dict) else StateItem()
            for item in doc.get("state_items", [])
        ]
        model = K1099Document(
            tax_year=doc.get("tax_year"),
            payer_name=payer.get("name", ""),
            payer_tin=payer.get("tin", ""),
            payer_address=payer.get("address", ""),
            payee_name=recipient.get("name", ""),
            payee_tin=recipient.get("tin", ""),
            payee_address=recipient.get("address", ""),
            account_number=doc.get("account_number", ""),
            box_1a_gross_amount=amounts.get("box_1a_gross_amount", 0.0),
            box_1b_card_not_present=amounts.get("box_1b_card_not_present", 0.0),
            box_2_merchant_category_code=doc.get("box_2_merchant_category_code", ""),
            box_3_number_of_payment_transactions=amounts.get("box_3_number_of_payment_transactions", 0.0),
            box_4_federal_income_tax_withheld=amounts.get("box_4_federal_income_tax_withheld", 0.0),
            monthly_totals=amounts.get("monthly_totals", []),
            state_items=state_items,
            ocr_quality=doc.get("ocr_quality"),
            source_pdf_path=meta.get("source_file", ""),
            extraction_engine_version=meta.get("extraction_engine_version", ""),
        )
        normalized = model.to_document_dict()
        normalized["doc_id"] = doc.get("doc_id")
        return normalized
    except Exception:
        return doc

def _normalize_1099r_with_schema(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize through the R1099Document schema when available."""
    try:
        from schemas.r_1099 import R1099Document, StateItem
    except Exception:
        return doc

    try:
        payer = doc.get("payer") or {}
        recipient = doc.get("recipient") or {}
        amounts = doc.get("amounts") or {}
        meta = doc.get("meta") or {}
        state_items = [
            item if isinstance(item, StateItem) else StateItem(**item) if isinstance(item, dict) else StateItem()
            for item in doc.get("state_items", [])
        ]
        model = R1099Document(
            tax_year=doc.get("tax_year"),
            payer_name=payer.get("name", ""),
            payer_tin=payer.get("tin", ""),
            payer_address=payer.get("address", ""),
            recipient_name=recipient.get("name", ""),
            recipient_tin=recipient.get("tin", ""),
            recipient_address=recipient.get("address", ""),
            account_number=doc.get("account_number", ""),
            box_1_gross_distribution=amounts.get("box_1_gross_distribution", 0.0),
            box_2a_taxable_amount=amounts.get("box_2a_taxable_amount", 0.0),
            box_2b_taxable_amount_not_determined=doc.get("box_2b_taxable_amount_not_determined", False),
            box_2b_total_distribution=doc.get("box_2b_total_distribution", False),
            box_3_capital_gain_included=amounts.get("box_3_capital_gain_included", 0.0),
            box_4_federal_income_tax_withheld=amounts.get("box_4_federal_income_tax_withheld", 0.0),
            box_5_employee_contributions_or_insurance_premiums=amounts.get("box_5_employee_contributions_or_insurance_premiums", 0.0),
            box_6_net_unrealized_appreciation=amounts.get("box_6_net_unrealized_appreciation", 0.0),
            box_7_distribution_codes=doc.get("box_7_distribution_codes", []),
            box_7_ira_sep_simple_indicator=doc.get("box_7_ira_sep_simple_indicator", False),
            box_8_other=amounts.get("box_8_other", 0.0),
            box_9a_total_distribution_pct=amounts.get("box_9a_total_distribution_pct", 0.0),
            box_9b_total_employee_contributions=amounts.get("box_9b_total_employee_contributions", 0.0),
            box_10_amount_allocable_to_IRR=amounts.get("box_10_amount_allocable_to_IRR", 0.0),
            box_11_first_year_designated_roth=doc.get("box_11_first_year_designated_roth"),
            box_12_fatca_filing_requirement=doc.get("box_12_fatca_filing_requirement", False),
            box_13_date_of_payment=doc.get("box_13_date_of_payment", ""),
            box_14_state_tax_withheld=doc.get("box_14_state_tax_withheld", []),
            box_15_state_id=doc.get("box_15_state_id", []),
            box_16_state_distribution=doc.get("box_16_state_distribution", []),
            state_items=state_items,
            ocr_quality=doc.get("ocr_quality"),
            source_pdf_path=meta.get("source_file", ""),
            extraction_engine_version=meta.get("extraction_engine_version", ""),
        )
        normalized = model.to_document_dict()
        normalized["doc_id"] = doc.get("doc_id")
        return normalized
    except Exception:
        return doc

def _normalize_1098_with_schema(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize through the F1098Document schema when available."""
    try:
        from schemas.f1098 import F1098Document
    except Exception:
        return doc

    try:
        payer = doc.get("payer") or {}
        recipient = doc.get("recipient") or {}
        amounts = doc.get("amounts") or {}
        meta = doc.get("meta") or {}
        model = F1098Document(
            tax_year=doc.get("tax_year"),
            lender_name=payer.get("name", ""),
            lender_tin=payer.get("tin", ""),
            lender_address=payer.get("address", ""),
            borrower_name=recipient.get("name", ""),
            borrower_tin=recipient.get("tin", ""),
            borrower_address=recipient.get("address", ""),
            box_1_mortgage_interest_received=amounts.get("box_1_mortgage_interest_received", 0.0),
            box_2_outstanding_mortgage_principal=amounts.get("box_2_outstanding_mortgage_principal", 0.0),
            box_3_mortgage_origination_date=doc.get("box_3_mortgage_origination_date", ""),
            box_4_refunded_interest=amounts.get("box_4_refunded_interest", 0.0),
            box_5_mortgage_insurance_premiums=amounts.get("box_5_mortgage_insurance_premiums", 0.0),
            box_6_points_paid_on_purchase=amounts.get("box_6_points_paid_on_purchase", 0.0),
            box_7_mortgaged_property_address=doc.get("box_7_mortgaged_property_address", ""),
            box_8_mortgaged_property_account_number=doc.get("box_8_mortgaged_property_account_number", ""),
            box_9_additional_mortgaged_property_info=doc.get("box_9_additional_mortgaged_property_info", ""),
            ocr_quality=doc.get("ocr_quality"),
            source_pdf_path=meta.get("source_file", ""),
            extraction_engine_version=meta.get("extraction_engine_version", ""),
        )
        normalized = model.to_document_dict()
        normalized["doc_id"] = doc.get("doc_id")
        return normalized
    except Exception:
        return doc

def _normalize_1095a_with_schema(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize through the F1095ADocument schema when available."""
    try:
        from schemas.f1095a import F1095ADocument, CoveredIndividual, MonthEntry
    except Exception:
        return doc

    try:
        recipient = doc.get("recipient") or {}
        issuer = doc.get("issuer") or {}
        months_raw = doc.get("months") or []
        covered = doc.get("covered_individuals") or []

        months = []
        for m in months_raw:
            if isinstance(m, MonthEntry):
                months.append(m)
            elif isinstance(m, dict):
                months.append(
                    MonthEntry(
                        month_index=m.get("month_index", 0),
                        monthly_premium=m.get("monthly_premium", 0.0),
                        slcsp_premium=m.get("slcsp_premium", 0.0),
                        advance_premium_tax_credit=m.get("advance_premium_tax_credit", 0.0),
                    )
                )
        covered_norm = []
        for ci in covered:
            if isinstance(ci, CoveredIndividual):
                covered_norm.append(ci)
            elif isinstance(ci, dict):
                covered_norm.append(
                    CoveredIndividual(
                        name=ci.get("name", ""),
                        ssn_or_tin=ci.get("ssn_or_tin", ""),
                        coverage_start=ci.get("coverage_start", ""),
                        coverage_end=ci.get("coverage_end", ""),
                    )
                )

        model = F1095ADocument(
            tax_year=doc.get("tax_year"),
            issuer_name=issuer.get("name", ""),
            issuer_ein=issuer.get("ein", ""),
            issuer_address=issuer.get("address", ""),
            recipient_name=recipient.get("name", ""),
            recipient_ssn_or_tin=recipient.get("tin", ""),
            recipient_address=recipient.get("address", ""),
            covered_individuals=covered_norm,
            months=months,
            ocr_quality=doc.get("ocr_quality"),
            source_pdf_path=(doc.get("meta") or {}).get("source_file", ""),
            extraction_engine_version=(doc.get("meta") or {}).get("extraction_engine_version", ""),
        )
        normalized = model.to_document_dict()
        normalized["doc_id"] = doc.get("doc_id")
        return normalized
    except Exception:
        return doc

def _normalize_941_with_schema(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize through the F941Document schema when available."""
    try:
        from schemas.f941 import F941Document
    except Exception:
        return doc

    try:
        employer = doc.get("employer") or {}
        amounts = doc.get("amounts") or {}
        meta = doc.get("meta") or {}
        model = F941Document(
            tax_year=doc.get("tax_year"),
            tax_quarter=doc.get("tax_quarter"),
            employer_name=employer.get("name", ""),
            employer_ein=employer.get("ein", ""),
            employer_address=employer.get("address", ""),
            line_1_num_employees=amounts.get("line_1_num_employees", 0.0),
            line_2_wages_tips_other_comp=amounts.get("line_2_wages_tips_other_comp", 0.0),
            line_3_income_tax_withheld=amounts.get("line_3_income_tax_withheld", 0.0),
            line_5a_taxable_ss_wages=amounts.get("line_5a_taxable_ss_wages", 0.0),
            line_5a_ss_tax=amounts.get("line_5a_ss_tax", 0.0),
            line_5b_taxable_ss_tips=amounts.get("line_5b_taxable_ss_tips", 0.0),
            line_5b_ss_tax_tips=amounts.get("line_5b_ss_tax_tips", 0.0),
            line_5c_taxable_medicare_wages=amounts.get("line_5c_taxable_medicare_wages", 0.0),
            line_5c_medicare_tax=amounts.get("line_5c_medicare_tax", 0.0),
            line_5d_taxable_addl_medicare_wages=amounts.get("line_5d_taxable_addl_medicare_wages", 0.0),
            line_5d_addl_medicare_tax=amounts.get("line_5d_addl_medicare_tax", 0.0),
            line_6_total_taxes_before_adjustments=amounts.get("line_6_total_taxes_before_adjustments", 0.0),
            line_7_current_quarter_fractions_of_cents_adjustment=amounts.get("line_7_current_quarter_fractions_of_cents_adjustment", 0.0),
            line_8_tip_adjustment=amounts.get("line_8_tip_adjustment", 0.0),
            line_9_sick_pay_adjustment=amounts.get("line_9_sick_pay_adjustment", 0.0),
            line_10_total_taxes_after_adjustments=amounts.get("line_10_total_taxes_after_adjustments", 0.0),
            line_11_total_deposits_for_quarter=amounts.get("line_11_total_deposits_for_quarter", 0.0),
            line_12_refundable_credits=amounts.get("line_12_refundable_credits", 0.0),
            line_13_total_taxes_after_credits=amounts.get("line_13_total_taxes_after_credits", 0.0),
            line_14_balance_due=amounts.get("line_14_balance_due", 0.0),
            line_15_overpayment=amounts.get("line_15_overpayment", 0.0),
            ocr_quality=doc.get("ocr_quality"),
            source_pdf_path=meta.get("source_file", ""),
            extraction_engine_version=meta.get("extraction_engine_version", ""),
        )
        normalized = model.to_document_dict()
        normalized["doc_id"] = doc.get("doc_id")
        return normalized
    except Exception:
        return doc

def _normalize_w9_with_schema(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize through the W9Document schema when available."""
    try:
        from schemas.w9 import W9Document
    except Exception:
        return doc

    try:
        meta = doc.get("meta") or {}
        model = W9Document(
            tax_year=doc.get("tax_year"),
            requestor_name=doc.get("requestor_name", ""),
            taxpayer_name=doc.get("taxpayer_name", ""),
            business_name_disregarded=doc.get("business_name_disregarded", ""),
            federal_tax_classification=doc.get("federal_tax_classification", ""),
            llc_tax_class_code=doc.get("llc_tax_class_code", ""),
            exempt_payee_code=doc.get("exempt_payee_code", ""),
            fatca_exemption_code=doc.get("fatca_exemption_code", ""),
            address_line1=doc.get("address_line1", ""),
            address_line2=doc.get("address_line2", ""),
            city=doc.get("city", ""),
            state=doc.get("state", ""),
            zip_code=doc.get("zip_code", ""),
            ssn=doc.get("ssn", ""),
            ein=doc.get("ein", ""),
            tin_raw=doc.get("tin_raw", ""),
            certification_signed_flag=doc.get("certification_signed_flag", False),
            certification_date=doc.get("certification_date", ""),
            ocr_quality=doc.get("ocr_quality"),
            source_pdf_path=meta.get("source_file", ""),
            extraction_engine_version=meta.get("extraction_engine_version", ""),
        )
        normalized = model.to_document_dict()
        normalized["doc_id"] = doc.get("doc_id")
        return normalized
    except Exception:
        return doc

def _normalize_1099b_with_schema(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize through the B1099Document schema when available."""
    try:
        from schemas.b_1099 import B1099Document, Transaction
    except Exception:
        return doc

    try:
        broker = doc.get("broker") or {}
        recipient = doc.get("recipient") or {}
        transactions_raw = doc.get("transactions") or []
        meta = doc.get("meta") or {}
        transactions = []
        for tx in transactions_raw:
            if isinstance(tx, Transaction):
                transactions.append(tx)
            elif isinstance(tx, dict):
                transactions.append(
                    Transaction(
                        description_of_property=tx.get("description_of_property", ""),
                        date_acquired=tx.get("date_acquired", ""),
                        date_sold=tx.get("date_sold", ""),
                        proceeds_gross=tx.get("proceeds_gross", 0.0),
                        cost_or_other_basis=tx.get("cost_or_other_basis", 0.0),
                        accrued_market_discount=tx.get("accrued_market_discount", 0.0),
                        wash_sale_disallowed=tx.get("wash_sale_disallowed", 0.0),
                        federal_income_tax_withheld=tx.get("federal_income_tax_withheld", 0.0),
                        type_of_gain_loss_code=tx.get("type_of_gain_loss_code", ""),
                        basis_reported_to_irs_flag=tx.get("basis_reported_to_irs_flag", False),
                        noncovered_security_flag=tx.get("noncovered_security_flag", False),
                        bartering_flag=tx.get("bartering_flag", False),
                        adjustments_code=tx.get("adjustments_code", ""),
                        adjustments_amount=tx.get("adjustments_amount", 0.0),
                    )
                )

        model = B1099Document(
            tax_year=doc.get("tax_year"),
            broker_name=broker.get("name", ""),
            broker_tin=broker.get("tin", ""),
            broker_address=broker.get("address", ""),
            recipient_name=recipient.get("name", ""),
            recipient_tin=recipient.get("tin", ""),
            recipient_address=recipient.get("address", ""),
            transactions=transactions,
            ocr_quality=doc.get("ocr_quality"),
            source_pdf_path=meta.get("source_file", ""),
            extraction_engine_version=meta.get("extraction_engine_version", ""),
        )
        normalized = model.to_document_dict()
        normalized["doc_id"] = doc.get("doc_id")
        return normalized
    except Exception:
        return doc

def _normalize_1098t_with_schema(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize through the Form1098T schema when available."""
    try:
        from schemas.t_1098 import Form1098T
    except Exception:
        return doc

    try:
        filer = doc.get("filer") or {}
        student = doc.get("student") or {}
        amounts = doc.get("amounts") or {}
        flags = doc.get("flags") or {}
        meta = doc.get("meta") or {}
        model = Form1098T(
            tax_year=doc.get("tax_year"),
            filer_name=filer.get("name", ""),
            filer_tin=filer.get("tin", ""),
            filer_address=filer.get("address", ""),
            student_name=student.get("name", ""),
            student_tin=student.get("tin", ""),
            student_address=student.get("address", ""),
            account_number=doc.get("account_number"),
            box1_payments_received=amounts.get("box1_payments_received", 0.0),
            box2_amounts_billed=amounts.get("box2_amounts_billed", 0.0),
            box4_adjustments_prior_year=amounts.get("box4_adjustments_prior_year", 0.0),
            box5_scholarships_grants=amounts.get("box5_scholarships_grants", 0.0),
            box6_adj_scholarships_prior_year=amounts.get("box6_adj_scholarships_prior_year", 0.0),
            box10_insurance_reimbursements=amounts.get("box10_insurance_reimbursements", 0.0),
            box3_reporting_method_changed=flags.get("box3_reporting_method_changed", False),
            box7_include_jan_mar=flags.get("box7_include_jan_mar", False),
            box8_at_least_half_time=flags.get("box8_at_least_half_time", False),
            box9_graduate_student=flags.get("box9_graduate_student", False),
            ocr_quality=doc.get("ocr_quality"),
            source_pdf_path=meta.get("source_file", ""),
            extraction_engine_version=meta.get("extraction_engine_version", ""),
        )
        normalized = model.to_document_dict()
        normalized["doc_id"] = doc.get("doc_id")
        return normalized
    except Exception:
        return doc

def _normalize_1099g_with_schema(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize through the Form1099G schema when available."""
    try:
        from schemas.g_1099 import Form1099G
    except Exception:
        return doc

    try:
        payer = doc.get("payer") or {}
        recipient = doc.get("recipient") or {}
        amounts = doc.get("amounts") or {}
        meta = doc.get("meta") or {}
        model = Form1099G(
            tax_year=doc.get("tax_year"),
            payer_name=payer.get("name", ""),
            payer_tin=payer.get("tin", ""),
            payer_address=payer.get("address", ""),
            recipient_name=recipient.get("name", ""),
            recipient_tin=recipient.get("tin", ""),
            recipient_address=recipient.get("address", ""),
            account_number=doc.get("account_number"),
            box1_unemployment_compensation=amounts.get("box1_unemployment_compensation", 0.0),
            box2_state_local_tax_refunds=amounts.get("box2_state_local_tax_refunds", 0.0),
            box3_box2_tax_year=doc.get("box3_box2_tax_year"),
            box4_federal_income_tax_withheld=amounts.get("box4_federal_income_tax_withheld", 0.0),
            box5_rtaa_payments=amounts.get("box5_rtaa_payments", 0.0),
            box6_taxable_grants=amounts.get("box6_taxable_grants", 0.0),
            box7_agricultural_payments=amounts.get("box7_agricultural_payments", 0.0),
            box8_trade_or_business_indicator=doc.get("box8_trade_or_business_indicator", False),
            box9_market_gain=amounts.get("box9_market_gain", 0.0),
            box10_state_tax_withheld=doc.get("box10_state_tax_withheld", []),
            box11_state_id=doc.get("box11_state_id", []),
            box12_state_income=doc.get("box12_state_income", []),
            ocr_quality=doc.get("ocr_quality"),
            source_pdf_path=meta.get("source_file", ""),
            extraction_engine_version=meta.get("extraction_engine_version", ""),
        )
        normalized = model.to_document_dict()
        normalized["doc_id"] = doc.get("doc_id")
        return normalized
    except Exception:
        return doc

def _normalize_1099s_with_schema(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize through the Form1099S schema when available."""
    try:
        from schemas.s_1099 import Form1099S
    except Exception:
        return doc

    try:
        filer = doc.get("filer") or {}
        transferor = doc.get("transferor") or {}
        amounts = doc.get("amounts") or {}
        meta = doc.get("meta") or {}
        model = Form1099S(
            tax_year=doc.get("tax_year"),
            filer_name=filer.get("name", ""),
            filer_tin=filer.get("tin", ""),
            filer_address=filer.get("address", ""),
            transferor_name=transferor.get("name", ""),
            transferor_tin=transferor.get("tin", ""),
            transferor_address=transferor.get("address", ""),
            account_number=doc.get("account_number"),
            property_address=doc.get("property_address"),
            property_desc=doc.get("property_desc"),
            box1_gross_proceeds=amounts.get("box1_gross_proceeds", 0.0),
            box2_property_or_services=doc.get("box2_property_or_services", False),
            box3_recipient_is_transferor=doc.get("box3_recipient_is_transferor", False),
            box4_federal_income_tax_withheld=amounts.get("box4_federal_income_tax_withheld", 0.0),
            box5_transferor_is_foreign=doc.get("box5_transferor_is_foreign", False),
            closing_date=doc.get("closing_date"),
            state_tax_withheld=doc.get("state_tax_withheld", []),
            state_id=doc.get("state_id", []),
            state_income=doc.get("state_income", []),
            ocr_quality=doc.get("ocr_quality"),
            source_pdf_path=meta.get("source_file", ""),
            extraction_engine_version=meta.get("extraction_engine_version", ""),
        )
        normalized = model.to_document_dict()
        normalized["doc_id"] = doc.get("doc_id")
        return normalized
    except Exception:
        return doc

def _normalize_1099c_with_schema(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize through the Form1099C schema when available."""
    try:
        from schemas.c_1099 import Form1099C
    except Exception:
        return doc

    try:
        creditor = doc.get("creditor") or {}
        debtor = doc.get("debtor") or {}
        amounts = doc.get("amounts") or {}
        meta = doc.get("meta") or {}
        model = Form1099C(
            tax_year=doc.get("tax_year"),
            creditor_name=creditor.get("name", ""),
            creditor_tin=creditor.get("tin", ""),
            creditor_address=creditor.get("address", ""),
            debtor_name=debtor.get("name", ""),
            debtor_tin=debtor.get("tin", ""),
            debtor_address=debtor.get("address", ""),
            account_number=doc.get("account_number"),
            box1_date_of_identifiable_event=doc.get("box1_date_of_identifiable_event"),
            box2_amount_of_debt_discharged=amounts.get("box2_amount_of_debt_discharged", 0.0),
            box3_interest_if_included=amounts.get("box3_interest_if_included", 0.0),
            box4_debt_description=doc.get("box4_debt_description"),
            box5_debtor_personally_liable=doc.get("box5_debtor_personally_liable", False),
            box6_identifiable_event_code=doc.get("box6_identifiable_event_code"),
            box7_fair_market_value_property=amounts.get("box7_fair_market_value_property", 0.0),
            state_tax_withheld=doc.get("state_tax_withheld", []),
            state_id=doc.get("state_id", []),
            state_income=doc.get("state_income", []),
            ocr_quality=doc.get("ocr_quality"),
            source_pdf_path=meta.get("source_file", ""),
            extraction_engine_version=meta.get("extraction_engine_version", ""),
        )
        normalized = model.to_document_dict()
        normalized["doc_id"] = doc.get("doc_id")
        return normalized
    except Exception:
        return doc

def _normalize_1099sa_with_schema(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize through the Form1099SA schema when available."""
    try:
        from schemas.sa_1099 import Form1099SA
    except Exception:
        return doc

    try:
        payer = doc.get("payer") or {}
        recipient = doc.get("recipient") or {}
        amounts = doc.get("amounts") or {}
        meta = doc.get("meta") or {}
        model = Form1099SA(
            tax_year=doc.get("tax_year"),
            payer_name=payer.get("name", ""),
            payer_tin=payer.get("tin", ""),
            payer_address=payer.get("address", ""),
            recipient_name=recipient.get("name", ""),
            recipient_tin=recipient.get("tin", ""),
            recipient_address=recipient.get("address", ""),
            account_number=doc.get("account_number"),
            box1_gross_distribution=amounts.get("box1_gross_distribution", 0.0),
            box2_earnings_on_excess_contributions=amounts.get("box2_earnings_on_excess_contributions", 0.0),
            box3_distribution_code=doc.get("box3_distribution_code", ""),
            box4_federal_income_tax_withheld=amounts.get("box4_federal_income_tax_withheld", 0.0),
            box5_fair_market_value_hsa_msa=amounts.get("box5_fair_market_value_hsa_msa", 0.0),
            hsa=doc.get("hsa", False),
            archer_msa=doc.get("archer_msa", False),
            ma_msa=doc.get("ma_msa", False),
            state_tax_withheld=doc.get("state_tax_withheld", []),
            state_id=doc.get("state_id", []),
            state_income=doc.get("state_income", []),
            ocr_quality=doc.get("ocr_quality"),
            source_pdf_path=meta.get("source_file", ""),
            extraction_engine_version=meta.get("extraction_engine_version", ""),
        )
        normalized = model.to_document_dict()
        normalized["doc_id"] = doc.get("doc_id")
        return normalized
    except Exception:
        return doc

def _normalize_5498_with_schema(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize through the Form5498 schema when available."""
    try:
        from schemas.f_5498 import Form5498
    except Exception:
        return doc

    try:
        trustee = doc.get("trustee") or {}
        participant = doc.get("participant") or {}
        amounts = doc.get("amounts") or {}
        flags = doc.get("flags") or {}
        meta = doc.get("meta") or {}
        model = Form5498(
            tax_year=doc.get("tax_year"),
            trustee_name=trustee.get("name", ""),
            trustee_tin=trustee.get("tin", ""),
            trustee_address=trustee.get("address", ""),
            participant_name=participant.get("name", ""),
            participant_tin=participant.get("tin", ""),
            participant_address=participant.get("address", ""),
            account_number=doc.get("account_number"),
            traditional_ira=flags.get("traditional_ira", False),
            roth_ira=flags.get("roth_ira", False),
            sep_ira=flags.get("sep_ira", False),
            simple_ira=flags.get("simple_ira", False),
            hsa=flags.get("hsa", False),
            esa_cesa=flags.get("esa_cesa", False),
            box1_ira_contributions=amounts.get("box1_ira_contributions", 0.0),
            box2_rollover_contributions=amounts.get("box2_rollover_contributions", 0.0),
            box3_roth_ira_conversion_amount=amounts.get("box3_roth_ira_conversion_amount", 0.0),
            box4_recharacterized_contributions=amounts.get("box4_recharacterized_contributions", 0.0),
            box5_fmv_of_account=amounts.get("box5_fmv_of_account", 0.0),
            box6_life_insurance_cost_in_ira=amounts.get("box6_life_insurance_cost_in_ira", 0.0),
            box7_roth_ira_contributions=amounts.get("box7_roth_ira_contributions", 0.0),
            box8_sep_contributions=amounts.get("box8_sep_contributions", 0.0),
            box9_simple_contributions=amounts.get("box9_simple_contributions", 0.0),
            box10_roth_ira_fmv_rollovers=amounts.get("box10_roth_ira_fmv_rollovers", 0.0),
            box11_required_minimum_distribution_indicator=doc.get("box11_required_minimum_distribution_indicator", False),
            box12_rmd_date=doc.get("box12_rmd_date"),
            box13_rmd_amount=amounts.get("box13_rmd_amount", 0.0),
            box14_hsa_msa_contributions=amounts.get("box14_hsa_msa_contributions", 0.0),
            box15_other_contributions=amounts.get("box15_other_contributions", 0.0),
            ocr_quality=doc.get("ocr_quality"),
            source_pdf_path=meta.get("source_file", ""),
            extraction_engine_version=meta.get("extraction_engine_version", ""),
        )
        normalized = model.to_document_dict()
        normalized["doc_id"] = doc.get("doc_id")
        return normalized
    except Exception:
        return doc

def _normalize_1099q_with_schema(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize through the Form1099Q schema when available."""
    try:
        from schemas.q_1099 import Form1099Q
    except Exception:
        return doc

    try:
        payer = doc.get("payer") or {}
        recipient = doc.get("recipient") or {}
        amounts = doc.get("amounts") or {}
        meta = doc.get("meta") or {}
        model = Form1099Q(
            tax_year=doc.get("tax_year"),
            payer_name=payer.get("name", ""),
            payer_tin=payer.get("tin", ""),
            payer_address=payer.get("address", ""),
            recipient_name=recipient.get("name", ""),
            recipient_tin=recipient.get("tin", ""),
            recipient_address=recipient.get("address", ""),
            account_number=doc.get("account_number"),
            box1_gross_distribution=amounts.get("box1_gross_distribution", 0.0),
            box2_earnings=amounts.get("box2_earnings", 0.0),
            box3_basis=amounts.get("box3_basis", 0.0),
            box4_trustee_to_trustee_transfer=doc.get("box4_trustee_to_trustee_transfer", False),
            box5_qualified_tuition_program=doc.get("box5_qualified_tuition_program", False),
            box6_life_insurance_distributed=doc.get("box6_life_insurance_distributed", False),
            qualified_tuition_program_529=doc.get("qualified_tuition_program_529", False),
            coverdell_esa=doc.get("coverdell_esa", False),
            state_tax_withheld=doc.get("state_tax_withheld", []),
            state_id=doc.get("state_id", []),
            state_income=doc.get("state_income", []),
            ocr_quality=doc.get("ocr_quality"),
            source_pdf_path=meta.get("source_file", ""),
            extraction_engine_version=meta.get("extraction_engine_version", ""),
        )
        normalized = model.to_document_dict()
        normalized["doc_id"] = doc.get("doc_id")
        return normalized
    except Exception:
        return doc
def _normalize_ssa1099_with_schema(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize through the SSA1099Document schema when available."""
    try:
        from schemas.ssa_1099 import SSA1099Document, StateItem
    except Exception:
        return doc

    try:
        payer = doc.get("payer") or {}
        beneficiary = doc.get("beneficiary") or {}
        amounts = doc.get("amounts") or {}
        meta = doc.get("meta") or {}
        state_items = [
            item if isinstance(item, StateItem) else StateItem(**item) if isinstance(item, dict) else StateItem()
            for item in doc.get("state_items", [])
        ]
        model = SSA1099Document(
            tax_year=doc.get("tax_year"),
            payer_name=payer.get("name", ""),
            payer_tin=payer.get("tin", ""),
            payer_address=payer.get("address", ""),
            beneficiary_name=beneficiary.get("name", ""),
            beneficiary_tin=beneficiary.get("tin", ""),
            beneficiary_address=beneficiary.get("address", ""),
            box_3_benefits_paid=amounts.get("box_3_benefits_paid", 0.0),
            box_4_benefits_repaid=amounts.get("box_4_benefits_repaid", 0.0),
            box_5_net_benefits=amounts.get("box_5_net_benefits", 0.0),
            box_6_voluntary_federal_tax_withheld=amounts.get("box_6_voluntary_federal_tax_withheld", 0.0),
            box_7_medicare_premiums=amounts.get("box_7_medicare_premiums", 0.0),
            box_8_other_deductions_or_adjustments=amounts.get("box_8_other_deductions_or_adjustments", 0.0),
            box_9_state_repayment=amounts.get("box_9_state_repayment", 0.0),
            state_items=state_items,
            ocr_quality=doc.get("ocr_quality"),
            source_pdf_path=meta.get("source_file", ""),
            extraction_engine_version=meta.get("extraction_engine_version", ""),
        )
        normalized = model.to_document_dict()
        normalized["doc_id"] = doc.get("doc_id")
        return normalized
    except Exception:
        return doc


def parse_w2_from_text(doc_id: str, text: str, used_ocr: bool) -> Dict[str, Any]:
    """Normalize extracted text into W-2 structured payload."""
    doc = _blank_w2(doc_id)
    extracted = extract_structured_fields(text)
    _apply_extracted_fields(doc, extracted)
    _populate_wages_from_text(doc, text)
    _apply_fallback_amounts(doc, text)
    doc["ocr_quality"] = _assign_ocr_quality(text, used_ocr)
    return doc


def _force_pdf_ocr(path_or_stream: str | Path | BytesIO) -> str:
    """Run OCR on a PDF source regardless of prior extraction attempts."""
    try:
        from pdf2image import convert_from_path, convert_from_bytes  # type: ignore
        import pytesseract  # type: ignore

        if isinstance(path_or_stream, (str, Path)):
            images = convert_from_path(str(path_or_stream), dpi=200)
        else:
            raw = path_or_stream.read() if hasattr(path_or_stream, "read") else path_or_stream
            images = convert_from_bytes(raw, dpi=200)
        ocr_texts = [pytesseract.image_to_string(img) for img in images]
        return "\n".join(ocr_texts)
    except Exception as exc:
        logger.warning("Forced OCR failed: %s", exc)
        return ""


def parse_document(path: str | Path) -> Dict[str, Any]:
    """Parse PDF/image/JSON into a structured dict with minimal heuristics."""
    p = Path(path)
    if p.suffix.lower() == ".json":
        return load_json_document(p)

    if p.suffix.lower() == ".pdf":
        pdf_bytes = p.read_bytes()
        doc_id = p.stem or uuid.uuid4().hex
        text, used_ocr = extract_text_from_pdf(p)
        form_type = _detect_form_type_from_text(text)

        if form_type == "1099-INT":
            doc = _blank_1099int(doc_id)
            form_fields = extract_acroform_fields(pdf_bytes)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099int_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099int_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099int_with_schema(doc)
            doc["meta"] = {"source_file": p.name}
            return doc
        if form_type == "1099-NEC":
            doc = _blank_1099nec(doc_id)
            form_fields = extract_acroform_fields(pdf_bytes)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099nec_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)  # reuse merge for payer/recipient/amounts/state
            text_doc = parse_1099nec_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099nec_with_schema(doc)
            doc["meta"] = {"source_file": p.name}
            return doc
        if form_type == "1099-MISC":
            doc = _blank_1099misc(doc_id)
            form_fields = extract_acroform_fields(pdf_bytes)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099misc_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099misc_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099misc_with_schema(doc)
            doc["meta"] = {"source_file": p.name}
            return doc
        if form_type == "1099-DIV":
            doc = _blank_1099div(doc_id)
            form_fields = extract_acroform_fields(pdf_bytes)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099div_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099div_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["box_7_foreign_country_or_possession"] = doc.get("box_7_foreign_country_or_possession") or text_doc.get("box_7_foreign_country_or_possession", "")
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099div_with_schema(doc)
            doc["meta"] = {"source_file": p.name}
            return doc
        if form_type == "1099-K":
            doc = _blank_1099k(doc_id)
            form_fields = extract_acroform_fields(pdf_bytes)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099k_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099k_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["box_2_merchant_category_code"] = doc.get("box_2_merchant_category_code") or text_doc.get("box_2_merchant_category_code", "")
            doc["account_number"] = doc.get("account_number") or text_doc.get("account_number", "")
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099k_with_schema(doc)
            doc["meta"] = {"source_file": p.name}
            return doc
        if form_type == "1099-R":
            doc = _blank_1099r(doc_id)
            form_fields = extract_acroform_fields(pdf_bytes)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099r_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099r_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            if "box_2b_taxable_amount_not_determined" in text_doc:
                doc["box_2b_taxable_amount_not_determined"] = text_doc["box_2b_taxable_amount_not_determined"]
            if "box_7_distribution_codes" in text_doc and text_doc["box_7_distribution_codes"]:
                doc["box_7_distribution_codes"] = text_doc["box_7_distribution_codes"]
            if "box_7_ira_sep_simple_indicator" in text_doc:
                doc["box_7_ira_sep_simple_indicator"] = text_doc["box_7_ira_sep_simple_indicator"]
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099r_with_schema(doc)
            doc["meta"] = {"source_file": p.name}
            return doc
        if form_type == "1099-G":
            doc = _blank_1099g(doc_id)
            form_fields = extract_acroform_fields(pdf_bytes)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099g_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099g_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099g_with_schema(doc)
            doc["meta"] = {"source_file": p.name}
            return doc
        if form_type == "1099-S":
            doc = _blank_1099s(doc_id)
            form_fields = extract_acroform_fields(pdf_bytes)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099s_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099s_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099s_with_schema(doc)
            doc["meta"] = {"source_file": p.name}
            return doc
        if form_type == "1099-C":
            doc = _blank_1099c(doc_id)
            form_fields = extract_acroform_fields(pdf_bytes)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099c_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099c_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099c_with_schema(doc)
            doc["meta"] = {"source_file": p.name}
            return doc
        if form_type == "1099-SA":
            doc = _blank_1099sa(doc_id)
            form_fields = extract_acroform_fields(pdf_bytes)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099sa_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099sa_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099sa_with_schema(doc)
            doc["meta"] = {"source_file": p.name}
            return doc
        if form_type == "5498":
            doc = _blank_5498(doc_id)
            form_fields = extract_acroform_fields(pdf_bytes)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_5498_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_5498_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_5498_with_schema(doc)
            doc["meta"] = {"source_file": p.name}
            return doc
        if form_type == "1099-Q":
            doc = _blank_1099q(doc_id)
            form_fields = extract_acroform_fields(pdf_bytes)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099q_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099q_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099q_with_schema(doc)
            doc["meta"] = {"source_file": p.name}
            return doc
        if form_type == "1098-T":
            doc = _blank_1098t(doc_id)
            form_fields = extract_acroform_fields(pdf_bytes)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1098t_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1098t_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1098t_with_schema(doc)
            doc["meta"] = {"source_file": p.name}
            return doc
        if form_type == "1098":
            doc = _blank_1098(doc_id)
            form_fields = extract_acroform_fields(pdf_bytes)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1098_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1098_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1098_with_schema(doc)
            doc["meta"] = {"source_file": p.name}
            return doc
        if form_type == "1095-A":
            doc = _blank_1095a(doc_id)
            form_fields = extract_acroform_fields(pdf_bytes)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1095a_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1095a_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1095a_with_schema(doc)
            doc["meta"] = {"source_file": p.name}
            return doc
        if form_type == "941":
            doc = _blank_941(doc_id)
            form_fields = extract_acroform_fields(pdf_bytes)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_941_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_941_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_941_with_schema(doc)
            doc["meta"] = {"source_file": p.name}
            return doc
        if form_type == "W-9":
            doc = _blank_w9(doc_id)
            form_fields = extract_acroform_fields(pdf_bytes)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_w9_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_w9_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_w9_with_schema(doc)
            doc["meta"] = {"source_file": p.name}
            return doc
        if form_type == "1099-B":
            doc = _blank_1099b(doc_id)
            form_fields = extract_acroform_fields(pdf_bytes)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099b_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099b_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099b_with_schema(doc)
            doc["meta"] = {"source_file": p.name}
            return doc
        if form_type == "1099-G":
            doc = _blank_1099g(doc_id)
            form_fields = extract_acroform_fields(pdf_bytes)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099g_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099g_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099g_with_schema(doc)
            doc["meta"] = {"source_file": p.name}
            return doc
        if form_type == "SSA-1099":
            doc = _blank_ssa1099(doc_id)
            form_fields = extract_acroform_fields(pdf_bytes)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                # SSA-1099 forms rarely provide structured fields; skip specific mapping for now
            text_doc = parse_ssa1099_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_ssa1099_with_schema(doc)
            doc["meta"] = {"source_file": p.name}
            return doc

        # Default to W-2 extraction
        doc = _blank_w2(doc_id)
        form_fields = extract_acroform_fields(pdf_bytes)
        if form_fields:
            logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
            mapped = map_w2_fields_from_form(form_fields)
            _merge_form_mapping(doc, mapped)

        text_doc = parse_w2_from_text(doc_id, text, used_ocr)
        doc = _merge_docs(doc, text_doc)
        doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
        if used_ocr:
            logger.info("Primary PDF extraction for %s relied on OCR fallback", doc_id)

        if _wages_missing(doc) and not used_ocr:
            logger.info("OCR fallback triggered for %s due to missing wage/tax fields", doc_id)
            ocr_text = _force_pdf_ocr(p)
            if ocr_text:
                ocr_doc = parse_w2_from_text(doc_id, ocr_text, used_ocr=True)
                doc = _merge_docs(doc, ocr_doc)
                doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), ocr_doc.get("ocr_quality", 1.0))

        if _wages_missing(doc):
            logger.warning("W-2 extraction incomplete for %s; key wage/tax fields still missing", doc_id)
        _log_missing_fields(doc)
        doc["meta"] = {"source_file": p.name}
        return doc

    if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}:
        text = extract_text_from_image(p)
        doc_id = p.stem or uuid.uuid4().hex
        doc = parse_w2_from_text(doc_id, text, used_ocr=True)
        _log_missing_fields(doc)
        doc["meta"] = {"source_file": p.name}
        return doc

    raise ValueError(f"Unsupported document type for {p}")


def parse_document_bytes(filename: str, data: bytes) -> Dict[str, Any]:
    """Parse uploaded bytes using the filename extension for routing."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".json":
        try:
            doc = json.loads(data.decode("utf-8"))
        except Exception as exc:
            raise ValueError("Invalid JSON payload") from exc
        if not isinstance(doc, dict):
            raise ValueError("Expected JSON object as document root.")
        return doc

        if suffix == ".pdf":
        doc_id = Path(filename).stem or uuid.uuid4().hex
        text, used_ocr = extract_text_from_pdf(BytesIO(data))
        form_type = _detect_form_type_from_text(text)

        if form_type == "1099-INT":
            doc = _blank_1099int(doc_id)
            form_fields = extract_acroform_fields(data)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099int_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099int_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099int_with_schema(doc)
            doc["meta"] = {"source_file": filename}
            return doc
        if form_type == "1099-NEC":
            doc = _blank_1099nec(doc_id)
            form_fields = extract_acroform_fields(data)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099nec_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099nec_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099nec_with_schema(doc)
            doc["meta"] = {"source_file": filename}
            return doc
        if form_type == "1099-MISC":
            doc = _blank_1099misc(doc_id)
            form_fields = extract_acroform_fields(data)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099misc_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099misc_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099misc_with_schema(doc)
            doc["meta"] = {"source_file": filename}
            return doc
        if form_type == "1099-DIV":
            doc = _blank_1099div(doc_id)
            form_fields = extract_acroform_fields(data)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099div_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099div_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["box_7_foreign_country_or_possession"] = doc.get("box_7_foreign_country_or_possession") or text_doc.get("box_7_foreign_country_or_possession", "")
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099div_with_schema(doc)
            doc["meta"] = {"source_file": filename}
            return doc
        if form_type == "1099-K":
            doc = _blank_1099k(doc_id)
            form_fields = extract_acroform_fields(data)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099k_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099k_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["box_2_merchant_category_code"] = doc.get("box_2_merchant_category_code") or text_doc.get("box_2_merchant_category_code", "")
            doc["account_number"] = doc.get("account_number") or text_doc.get("account_number", "")
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099k_with_schema(doc)
            doc["meta"] = {"source_file": filename}
            return doc
        if form_type == "1099-R":
            doc = _blank_1099r(doc_id)
            form_fields = extract_acroform_fields(data)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099r_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099r_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            if "box_2b_taxable_amount_not_determined" in text_doc:
                doc["box_2b_taxable_amount_not_determined"] = text_doc["box_2b_taxable_amount_not_determined"]
            if "box_7_distribution_codes" in text_doc and text_doc["box_7_distribution_codes"]:
                doc["box_7_distribution_codes"] = text_doc["box_7_distribution_codes"]
            if "box_7_ira_sep_simple_indicator" in text_doc:
                doc["box_7_ira_sep_simple_indicator"] = text_doc["box_7_ira_sep_simple_indicator"]
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099r_with_schema(doc)
            doc["meta"] = {"source_file": filename}
            return doc
        if form_type == "1099-G":
            doc = _blank_1099g(doc_id)
            form_fields = extract_acroform_fields(data)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099g_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099g_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099g_with_schema(doc)
            doc["meta"] = {"source_file": filename}
            return doc
        if form_type == "1099-S":
            doc = _blank_1099s(doc_id)
            form_fields = extract_acroform_fields(data)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099s_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099s_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099s_with_schema(doc)
            doc["meta"] = {"source_file": filename}
            return doc
        if form_type == "1099-C":
            doc = _blank_1099c(doc_id)
            form_fields = extract_acroform_fields(data)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099c_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099c_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099c_with_schema(doc)
            doc["meta"] = {"source_file": filename}
            return doc
        if form_type == "1099-SA":
            doc = _blank_1099sa(doc_id)
            form_fields = extract_acroform_fields(data)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099sa_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099sa_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099sa_with_schema(doc)
            doc["meta"] = {"source_file": filename}
            return doc
        if form_type == "5498":
            doc = _blank_5498(doc_id)
            form_fields = extract_acroform_fields(data)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_5498_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_5498_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_5498_with_schema(doc)
            doc["meta"] = {"source_file": filename}
            return doc
        if form_type == "1099-Q":
            doc = _blank_1099q(doc_id)
            form_fields = extract_acroform_fields(data)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099q_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099q_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099q_with_schema(doc)
            doc["meta"] = {"source_file": filename}
            return doc
        if form_type == "1098-T":
            doc = _blank_1098t(doc_id)
            form_fields = extract_acroform_fields(data)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1098t_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1098t_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1098t_with_schema(doc)
            doc["meta"] = {"source_file": filename}
            return doc
        if form_type == "1098":
            doc = _blank_1098(doc_id)
            form_fields = extract_acroform_fields(data)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1098_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1098_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1098_with_schema(doc)
            doc["meta"] = {"source_file": filename}
            return doc
        if form_type == "1095-A":
            doc = _blank_1095a(doc_id)
            form_fields = extract_acroform_fields(data)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1095a_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1095a_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1095a_with_schema(doc)
            doc["meta"] = {"source_file": filename}
            return doc
        if form_type == "941":
            doc = _blank_941(doc_id)
            form_fields = extract_acroform_fields(data)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_941_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_941_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_941_with_schema(doc)
            doc["meta"] = {"source_file": filename}
            return doc
        if form_type == "W-9":
            doc = _blank_w9(doc_id)
            form_fields = extract_acroform_fields(data)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_w9_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_w9_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_w9_with_schema(doc)
            doc["meta"] = {"source_file": filename}
            return doc
        if form_type == "1099-B":
            doc = _blank_1099b(doc_id)
            form_fields = extract_acroform_fields(data)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
                mapped = map_1099b_fields_from_form(form_fields)
                doc = _merge_1099int(doc, mapped)
            text_doc = parse_1099b_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_1099b_with_schema(doc)
            doc["meta"] = {"source_file": filename}
            return doc
        if form_type == "SSA-1099":
            doc = _blank_ssa1099(doc_id)
            form_fields = extract_acroform_fields(data)
            if form_fields:
                logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
            text_doc = parse_ssa1099_from_text(doc_id, text, used_ocr)
            doc = _merge_1099int(doc, text_doc)
            doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
            doc = _normalize_ssa1099_with_schema(doc)
            doc["meta"] = {"source_file": filename}
            return doc

        doc = _blank_w2(doc_id)
        form_fields = extract_acroform_fields(data)
        if form_fields:
            logger.info("AcroForm fields detected for %s: %d", doc_id, len(form_fields))
            mapped = map_w2_fields_from_form(form_fields)
            _merge_form_mapping(doc, mapped)

        text_doc = parse_w2_from_text(doc_id, text, used_ocr)
        doc = _merge_docs(doc, text_doc)
        doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), text_doc.get("ocr_quality", 1.0))
        if used_ocr:
            logger.info("Primary PDF extraction for %s relied on OCR fallback", doc_id)

        if _wages_missing(doc) and not used_ocr:
            logger.info("OCR fallback triggered for %s due to missing wage/tax fields", doc_id)
            ocr_text = _force_pdf_ocr(BytesIO(data))
            if ocr_text:
                ocr_doc = parse_w2_from_text(doc_id, ocr_text, used_ocr=True)
                doc = _merge_docs(doc, ocr_doc)
                doc["ocr_quality"] = min(doc.get("ocr_quality", 1.0), ocr_doc.get("ocr_quality", 1.0))

        if _wages_missing(doc):
            logger.warning("W-2 extraction incomplete for %s; key wage/tax fields still missing", doc_id)
        _log_missing_fields(doc)
        doc["meta"] = {"source_file": filename}
        return doc

    if suffix in {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}:
        text = extract_text_from_image_bytes(data)
        doc_id = Path(filename).stem or uuid.uuid4().hex
        doc = parse_w2_from_text(doc_id, text, used_ocr=True)
        _log_missing_fields(doc)
        doc["meta"] = {"source_file": filename}
        return doc

    raise ValueError(f"Unsupported file type: {suffix or 'unknown'}")
