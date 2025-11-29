"""Enhanced W-2 rule definitions with normalization and tolerances."""

MASKED_SSN_PATTERNS = [
    r"^\d{3}-?\d{2}-?\d{4}$",
    r"^X{3}-?X{2}-?\d{4}$",
    r"^\d{3}-?\d{2}-?X{4}$",
    r"^XXX-XX-\d{4}$",
    r"^000-00-XXXX$",
]


def _regex_union(patterns):
    return "(" + "|".join(patterns) + ")"


RULES = [
    {
        "id": "W2_SSN_FORMAT",
        "form_types": ["W2"],
        "name": "Taxpayer SSN format invalid",
        "severity": "warning",
        "description": "Taxpayer SSN is missing or not in a valid or masked format.",
        "condition": {
            "type": "expression",
            "expr": f"not re_match('{_regex_union(MASKED_SSN_PATTERNS)}', (taxpayer_ssn or '').strip())",
        },
        "references": [
            {"source": "IRS W-2 Instructions", "url": "https://www.irs.gov/forms-pubs/about-form-w-2"},
        ],
        "fields": ["taxpayer.ssn"],
    },
    {
        "id": "W2_EIN_FORMAT",
        "form_types": ["W2"],
        "name": "Employer EIN format needs review",
        "severity": "warning",
        "description": "Employer EIN should be 9 digits (XX-XXXXXXX).",
        "condition": {
            "type": "expression",
            "expr": "not re_match('^(\\d{2}-?\\d{7})$', (employer_ein or '').strip())",
        },
        "references": [
            {"source": "IRS W-2 Instructions", "url": "https://www.irs.gov/forms-pubs/about-form-w-2"},
        ],
        "fields": ["employer.ein"],
    },
    {
        "id": "W2_SS_TAX_MATCH",
        "form_types": ["W2"],
        "name": "Social Security tax outside tolerance",
        "severity": "warning",
        "description": "Social Security tax withheld differs from Box 3 wages x 6.2% beyond $2 tolerance.",
        "condition": {
            "type": "expression",
            "expr": "abs(get('wages.social_security_tax_withheld', 0) - get('wages.social_security_wages', 0) * 0.062) > 2",
        },
        "references": [
            {"source": "IRS Pub. 15", "url": "https://www.irs.gov/publications/p15"},
        ],
        "fields": ["wages.social_security_wages", "wages.social_security_tax_withheld"],
    },
    {
        "id": "W2_MEDICARE_TAX_MATCH",
        "form_types": ["W2"],
        "name": "Medicare tax outside tolerance",
        "severity": "warning",
        "description": "Medicare tax withheld differs from Box 5 wages x 1.45% beyond $2 tolerance.",
        "condition": {
            "type": "expression",
            "expr": "abs(get('wages.medicare_tax_withheld', 0) - get('wages.medicare_wages', 0) * 0.0145) > 2",
        },
        "references": [
            {"source": "IRS Pub. 15", "url": "https://www.irs.gov/publications/p15"},
        ],
        "fields": ["wages.medicare_wages", "wages.medicare_tax_withheld"],
    },
    {
        "id": "W2_BOX1_VS_BOX3_5_RELATION",
        "form_types": ["W2"],
        "name": "Box 1 differs from Box 3/5",
        "severity": "warning",
        "description": "Box 1 wages differ from Social Security or Medicare wages; pre-tax deductions may apply.",
        "condition": {
            "type": "expression",
            "expr": "wages_tips_other > 0 and (abs(wages_tips_other - social_security_wages) > year_params.get('tolerance', 1.0) or abs(wages_tips_other - medicare_wages) > year_params.get('tolerance', 1.0))",
        },
        "references": [
            {"source": "IRS W-2 Instructions", "url": "https://www.irs.gov/forms-pubs/about-form-w-2"},
        ],
        "fields": ["wages.wages_tips_other", "wages.social_security_wages", "wages.medicare_wages"],
    },
    {
        "id": "W2_YEAR_CONSISTENCY",
        "form_types": ["W2"],
        "name": "Tax year mismatch with document text",
        "severity": "warning",
        "description": "Tax year differs from detected year in document text by more than two years.",
        "condition": {
            "type": "expression",
            "expr": "tax_year and detected_years and all(abs(int(tax_year) - int(y)) > 2 for y in detected_years)",
        },
        "references": [
            {"source": "IRS W-2 Instructions", "url": "https://www.irs.gov/forms-pubs/about-form-w-2"},
        ],
        "fields": ["tax_year"],
    },
    {
        "id": "W2_EIN_VALID_CHECKSUM",
        "form_types": ["W2"],
        "name": "Employer EIN format/length needs review",
        "severity": "warning",
        "description": "Employer EIN should be reviewed; checksum not enforced but must be 9 digits.",
        "condition": {
            "type": "expression",
            "expr": "not re_match('^(\\d{2}-?\\d{7})$', (employer_ein or '').strip())",
        },
        "references": [
            {"source": "IRS W-2 Instructions", "url": "https://www.irs.gov/forms-pubs/about-form-w-2"},
        ],
        "fields": ["employer.ein"],
    },
]
