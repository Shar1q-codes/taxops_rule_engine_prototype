"""Context loader for tax-year-specific limits and rates."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml


CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "tax_years.yaml"


def _validate_year_entry(year: int, data: Dict[str, Any]) -> None:
    """Validate that a single tax year entry contains required keys."""
    if not isinstance(data, dict):
        raise ValueError(f"Config for tax year {year} must be a mapping.")
    limits = data.get("limits", {})
    rates = data.get("rates", {})
    missing = []
    if "social_security_wage_base" not in limits:
        missing.append("limits.social_security_wage_base")
    if "social_security_rate" not in rates:
        missing.append("rates.social_security_rate")
    if "medicare_rate" not in rates:
        missing.append("rates.medicare_rate")
    if missing:
        missing_keys = ", ".join(missing)
        raise ValueError(f"Config for tax year {year} missing required keys: {missing_keys}")


@lru_cache(maxsize=1)
def load_tax_year_config() -> Dict[int, Dict[str, Any]]:
    """
    Load tax-year configuration from config/tax_years.yaml.

    Returns a dict mapping tax_year (int) -> config dict with keys:
      - "limits"
      - "rates"
    """
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Tax year config not found at {CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    config: Dict[int, Dict[str, Any]] = {}
    for raw_year, data in raw.items():
        try:
            year_int = int(raw_year)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid tax year key: {raw_year}") from exc
        _validate_year_entry(year_int, data or {})
        config[year_int] = data
    return config


def get_context_for_year(tax_year: int) -> Dict[str, Any]:
    """
    Return a context dict for the given tax year, suitable to be passed
    into rule_engine.core.apply_rules.

    Shape:
    {
        "limits": {
            "social_security_wage_base": <float>
        },
        "rates": {
            "social_security_rate": <float>,
            "medicare_rate": <float>
        }
    }

    If the tax_year is not defined, raise a ValueError with a clear message.
    """
    config = load_tax_year_config()
    if tax_year not in config:
        raise ValueError(f"Unsupported tax year: {tax_year}")
    return config[tax_year]
