import pytest

from rule_engine.context import get_context_for_year, load_tax_year_config


def test_get_context_for_year_known_year():
    ctx = get_context_for_year(2024)
    assert "limits" in ctx and "rates" in ctx
    assert ctx["limits"]["social_security_wage_base"] > 0
    ss_rate = ctx["rates"]["social_security_rate"]
    medicare_rate = ctx["rates"]["medicare_rate"]
    assert 0 < ss_rate < 1
    assert 0 < medicare_rate < 1


def test_get_context_for_year_unknown_year_raises():
    with pytest.raises(ValueError) as excinfo:
        get_context_for_year(1999)
    assert "1999" in str(excinfo.value)


def test_load_tax_year_config_caches():
    first = load_tax_year_config()
    second = load_tax_year_config()
    assert first is second
