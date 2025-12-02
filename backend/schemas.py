from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


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


class AuditDocumentMetadata(BaseModel):
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
    document_metadata: AuditDocumentMetadata
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


class User(BaseModel):
    id: str
    email: str
    name: str
    roles: List[str] = Field(default_factory=list)
    firmId: Optional[str] = None


class EngagementSummary(BaseModel):
    id: str
    clientId: str
    name: str
    period: str
    status: str
    progress: int
    risk: str
    summary: Dict[str, Any]
    createdAt: datetime
    updatedAt: datetime


class Client(BaseModel):
    id: str
    name: str
    code: str
    status: str
    industry: str
    risk: str
    yearEnd: str
    createdAt: datetime
    updatedAt: datetime
    engagements: Optional[List[EngagementSummary]] = None


class MeResponse(BaseModel):
    user: User


class DomainStats(BaseModel):
    domain: str
    high: int
    medium: int
    low: int
    total: int


class EngagementStatsResponse(BaseModel):
    engagement_id: str
    domains: List[DomainStats]
    totals: Dict[str, int]


class DocumentMetadata(BaseModel):
    id: int
    engagement_id: str
    filename: str
    type: str
    amount: Optional[float] = None
    date: Optional[date] = None
    counterparty: Optional[str] = None
    external_ref: Optional[str] = None
    uploaded_at: datetime
    uploaded_by: str

    class Config:
        orm_mode = True


class DocumentListResponse(BaseModel):
    documents: List[DocumentMetadata]


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    firm_id: Optional[str] = None
    exp: Optional[int] = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class UserRead(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    is_active: bool


class FirmCreate(BaseModel):
    name: str


class FirmRead(BaseModel):
    id: str
    name: str


class RegisterFirmRequest(BaseModel):
    firm: FirmCreate
    user: UserCreate


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    firm_id: Optional[str] = None


class MeAuthResponse(BaseModel):
    user: UserRead
    firm: FirmRead
    roles: List[str] = Field(default_factory=list)
