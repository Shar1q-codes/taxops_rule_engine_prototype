from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Citation(BaseModel):
    label: str
    url: str


class Finding(BaseModel):
    id: str
    code: str
    severity: str
    rule_type: Optional[str] = None
    category: Optional[str] = None
    message: str
    doc_type: str
    tax_year: int
    fields: List[str] = Field(default_factory=list)
    field_paths: List[str] = Field(default_factory=list)
    citations: List[Citation] = Field(default_factory=list)
    rule_source: Optional[str] = None
    condition: Optional[str] = None
    extras: Dict[str, Any] = Field(default_factory=dict)
    summary: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class Summary(BaseModel):
    total_rules_evaluated: int
    total_findings: int
    by_severity: Dict[str, int]
    by_rule_type: Dict[str, int]


class DocumentMetadata(BaseModel):
    filename: Optional[str] = None
    content_type: Optional[str] = None
    pages: Optional[int] = None
    source: Optional[str] = None


class EngineInfo(BaseModel):
    ruleset: Optional[str] = None
    version: Optional[str] = None
    evaluation_time_ms: Optional[int] = None


class AuditResponse(BaseModel):
    request_id: str
    doc_id: str
    doc_type: str
    tax_year: int
    received_at: datetime
    processed_at: datetime
    status: str
    summary: Summary
    document_metadata: DocumentMetadata
    findings: List[Finding]
    engine: EngineInfo


class AuditReportParams(BaseModel):
    doc_type: Optional[str] = None
    tax_year: Optional[int] = None


class FirmInfo(BaseModel):
    id: str
    name: str
    logo_url: Optional[str] = None


class FirmSummary(BaseModel):
    totalClients: int
    activeEngagements: int
    highSeverityFindings: int
    upcomingReports: int
