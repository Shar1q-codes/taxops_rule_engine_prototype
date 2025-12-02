from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


DomainLiteral = Literal[
    "books",
    "income",
    "expense",
    "bank",
    "payroll",
    "inventory",
    "liabilities",
    "assets",
    "compliance",
    "documents",
    "controls",
]


class DomainFinding(BaseModel):
    id: str
    engagement_id: str
    domain: DomainLiteral
    severity: Literal["low", "medium", "high", "critical"]
    code: str
    message: str
    account_code: Optional[str] = None
    transaction_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


def make_finding_id(domain: str, code: str, idx: int) -> str:
    return f"f-{domain}-{code}-{idx}"


__all__ = ["DomainFinding", "DomainLiteral", "make_finding_id"]
