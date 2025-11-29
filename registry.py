"""In-memory registry for production-grade tax audit rules."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, DefaultDict, Dict, Iterable, List, Mapping, Sequence

try:  # pragma: no cover - allow running as script/module
    from .loader import load_all_rules, load_year_parameters
except ImportError:  # pragma: no cover - fallback for direct execution
    from loader import load_all_rules, load_year_parameters

try:
    from .rules import w2_rules_v2
except Exception:  # pragma: no cover - optional extension
    w2_rules_v2 = None  # type: ignore

YEAR_PARAMS = load_year_parameters()


def get_year_params(year: int) -> Mapping[str, Any]:
    if year in YEAR_PARAMS:
        params = dict(YEAR_PARAMS[year])
        params["_year"] = year
        return params
    return {}


class RuleRegistry:
    """Indexes rules by form type and stores per-year parameters."""

    def __init__(
        self,
        rules: Iterable[Mapping[str, Any]] | None = None,
        year_parameters: Mapping[int, Mapping[str, Any]] | None = None,
    ) -> None:
        base_rules = list(rules) if rules is not None else load_all_rules()
        if w2_rules_v2 and hasattr(w2_rules_v2, "RULES"):
            base_rules.extend(getattr(w2_rules_v2, "RULES"))
        self._all_rules = base_rules
        self._year_params = dict(year_parameters) if year_parameters is not None else YEAR_PARAMS
        self._rules_by_form: DefaultDict[str, List[Mapping[str, Any]]] = defaultdict(list)
        self._build_index()

    @property
    def year_parameters(self) -> Dict[int, Mapping[str, Any]]:
        return dict(self._year_params)

    @property
    def supported_years(self) -> Sequence[int]:
        return tuple(sorted(self._year_params.keys()))

    def _build_index(self) -> None:
        for rule in self._all_rules:
            forms = rule.get("form_types") or []
            if not isinstance(forms, list):
                continue
            for form in forms:
                if not form:
                    continue
                self._rules_by_form[form.upper()].append(rule)

    def get_rules(self, form_type: str | None) -> List[Mapping[str, Any]]:
        if not form_type:
            return []
        return list(self._rules_by_form.get(form_type.upper(), []))

    def get_year_params(self, tax_year: int | None) -> Mapping[str, Any]:
        if tax_year is None:
            return {}
        return get_year_params(tax_year)


def build_default_registry() -> RuleRegistry:
    """Construct a registry using on-disk YAML configuration."""
    return RuleRegistry()
