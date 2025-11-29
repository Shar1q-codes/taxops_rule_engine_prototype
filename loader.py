"""Loader utilities for rule and parameter YAML files."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml


PACKAGE_ROOT = Path(__file__).resolve().parent
RULES_DIR = PACKAGE_ROOT / "rules"
YEAR_PARAM_DIR = PACKAGE_ROOT / "year_params"


def _is_supported_rule_file(path: Path) -> bool:
    """Only load the new core rule files to avoid mixing with legacy YAMLs."""
    if not path.name.endswith(".yaml"):
        return False
    if path.name == "1040_recon.yaml":
        return True
    return path.name.endswith("_core.yaml")


def _load_yaml_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or []


def _normalize_rules(source: Path, raw: Any) -> List[Dict[str, Any]]:
    """Normalize rule YAML payloads to a flat list of dicts."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        rules = raw.get("rules") or raw.get("data") or []
    elif isinstance(raw, list):
        rules = raw
    else:
        return []

    normalized: List[Dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        # Attach source file for observability/debugging.
        rule["_source"] = source.name
        normalized.append(rule)
    return normalized


@lru_cache(maxsize=1)
def load_all_rules(rules_dir: Path | str | None = None) -> List[Dict[str, Any]]:
    """Load all supported rule YAML files into memory."""
    directory = Path(rules_dir) if rules_dir else RULES_DIR
    if not directory.exists():
        raise FileNotFoundError(f"Rules directory not found: {directory}")

    all_rules: List[Dict[str, Any]] = []
    for path in sorted(directory.glob("*.yaml")):
        if not _is_supported_rule_file(path):
            continue
        raw = _load_yaml_file(path)
        all_rules.extend(_normalize_rules(path, raw))
    return all_rules


@lru_cache(maxsize=1)
def load_year_parameters(param_dir: Path | str | None = None) -> Dict[int, Dict[str, Any]]:
    """Load per-year parameter YAML files."""
    directory = Path(param_dir) if param_dir else YEAR_PARAM_DIR
    if not directory.exists():
        raise FileNotFoundError(f"Year parameter directory not found: {directory}")

    params: Dict[int, Dict[str, Any]] = {}
    for path in sorted(directory.glob("*.yaml")):
        try:
            year = int(path.stem)
        except ValueError as exc:  # noqa: PERF203 - explicit handling for clarity
            raise ValueError(f"Invalid year param filename: {path.name}") from exc
        data = _load_yaml_file(path)
        if not isinstance(data, dict):
            raise ValueError(f"Year parameter file must be a mapping: {path}")
        # Support either a flat mapping or a nested mapping keyed by the year.
        if set(data.keys()) == {year}:
            data = data[year]
        elif set(data.keys()) == {str(year)}:
            data = data[str(year)]
        if not isinstance(data, dict):
            raise ValueError(f"Year parameter file must map to a dict of values: {path}")
        params[year] = data
    if not params:
        raise ValueError(f"No year parameter files found in {directory}")
    return params


def reload_caches() -> None:
    """Clear cached loaders (useful for tests)."""
    load_all_rules.cache_clear()
    load_year_parameters.cache_clear()
