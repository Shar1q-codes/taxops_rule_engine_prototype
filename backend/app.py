"""FastAPI wrapper around the Corallo TaxOps auditor inference pipeline.

This service exposes a single `/audit-document` endpoint that accepts PDF/Image/JSON uploads,
verifies Firebase-issued JWTs, routes the file through lightweight parsing, and returns
deterministic + LLM findings from the existing auditor_inference package.
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
import io
import json
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy.orm import Session

# Ensure the repo root (auditor_inference, auditor, etc.) is importable when deployed.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from engine import rule_engine  # noqa: E402
from auditor_inference.document_extraction import parse_document_bytes  # noqa: E402
from auditor_inference.inference import audit_document  # noqa: E402
from backend.reporting import render_audit_report  # noqa: E402
from backend.schemas import (  # noqa: E402
    AuditDocumentMetadata,
    AuditResponse,
    Citation,
    DocumentListResponse,
    DocumentMetadata,
    EngineInfo,
    Finding,
    Summary,
    FirmInfo,
    FirmSummary,
    User,
    Client,
    EngagementSummary,
    MeResponse,
    EngagementStatsResponse,
    MeAuthResponse,
)
from backend.accounting_store import (
    get_transactions,
    get_trial_balance,
    save_transactions,
    save_trial_balance,
    save_gl_entries,
    save_bank_entries,
    save_payroll_entries,
    save_payroll_employees,
    save_inventory_items,
    save_inventory_movements,
    save_loans,
    save_loan_periods,
    save_ap_entries,
    save_assets,
    save_depreciation_entries,
    save_tax_returns,
    save_books_tax,
)  # noqa: E402
from backend.books_ingestion import (  # noqa: E402
    parse_tb_rows_from_csv,
    parse_tb_rows_from_list,
    parse_transactions_from_csv,
    parse_transactions_from_rows,
    parse_gl_entries_from_csv,
    parse_gl_entries_from_rows,
)
from backend.bank_ingestion import parse_bank_csv  # noqa: E402
from backend.bank_rules import run_bank_rules  # noqa: E402
from backend.books_rules import BookFinding, run_books_rules  # noqa: E402
from backend.domain_rules import DomainFinding  # noqa: E402
from backend.expense_rules import run_expense_rules  # noqa: E402
from backend.income_rules import run_income_rules  # noqa: E402
from backend.payroll_ingestion import parse_payroll_employee_csv, parse_payroll_entries_csv  # noqa: E402
from backend.payroll_rules import run_payroll_rules  # noqa: E402
from backend.inventory_ingestion import parse_inventory_items_csv, parse_inventory_movements_csv  # noqa: E402
from backend.inventory_rules import run_inventory_rules  # noqa: E402
from backend.db import get_db, init_db  # noqa: E402
from backend.db_models import ClientORM, DocumentLinkORM, DocumentORM, EngagementORM, FindingORM  # noqa: E402
from backend.seed import seed_demo_data  # noqa: E402
from backend.liabilities_ingestion import parse_ap_entries_csv, parse_loan_periods_csv, parse_loans_csv  # noqa: E402
from backend.liabilities_rules import run_liabilities_rules  # noqa: E402
from backend.assets_ingestion import parse_assets_csv, parse_depreciation_csv  # noqa: E402
from backend.assets_rules import run_assets_rules  # noqa: E402
from backend.compliance_ingestion import parse_books_tax_csv, parse_returns_csv  # noqa: E402
from backend.compliance_rules import run_compliance_rules  # noqa: E402
from backend.books_schemas import GLIngestResponse, TrialBalanceIngestResponse  # noqa: E402
from backend.findings_persistence import save_domain_findings  # noqa: E402
from backend.engagement_stats import compute_engagement_stats  # noqa: E402
from backend.docs_matching import match_document_to_bank_entries  # noqa: E402
from backend.docs_rules import run_document_rules  # noqa: E402
from backend.controls_rules import run_controls_rules  # noqa: E402
from backend.deps import RequestContext, get_current_context  # noqa: E402
from backend.routers import auth as auth_router  # noqa: E402
from backend.security import decode_token  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402

logger = logging.getLogger("taxops-api")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


def get_settings() -> Dict[str, Any]:
    base_dir = ROOT_DIR
    llm_endpoint = os.getenv("LLM_ENDPOINT")
    skip_llm = os.getenv("AUDITOR_SKIP_LLM", "true").lower() == "true"
    if llm_endpoint:
        # If a remote LLM is provided we can allow LLM usage unless explicitly disabled.
        skip_llm = os.getenv("AUDITOR_SKIP_LLM", "false").lower() == "true"
    allowed_raw = os.getenv("ALLOWED_ORIGINS", "*")
    allowed_list = [o.strip() for o in allowed_raw.split(",") if o.strip()]
    return {
        "chunk_index_path": os.getenv("CHUNK_INDEX_PATH", str(base_dir / "sample_data" / "chunk_index.jsonl")),
        "base_model": os.getenv("AUDITOR_BASE_MODEL", "mistralai/Mistral-7B-v0.1"),
        "adapter_dir": os.getenv("AUDITOR_ADAPTER_DIR", str(base_dir / "outputs" / "auditor_mistral_lora")),
        "merge_strategy": os.getenv("AUDITOR_MERGE_STRATEGY", "no_duplicates"),
        "device": os.getenv("AUDITOR_DEVICE", "cpu"),
        "use_4bit": os.getenv("AUDITOR_USE_4BIT", "false").lower() == "true",
        "max_new_tokens": int(os.getenv("AUDITOR_MAX_NEW_TOKENS", "256")),
        "temperature": float(os.getenv("AUDITOR_TEMPERATURE", "0.1")),
        "top_p": float(os.getenv("AUDITOR_TOP_P", "0.9")),
        "do_sample": os.getenv("AUDITOR_DO_SAMPLE", "false").lower() == "true",
        "skip_llm": skip_llm,
        "llm_endpoint": llm_endpoint,
        "http_timeout": int(os.getenv("AUDITOR_HTTP_TIMEOUT", "60")),
        "allowed_origins": allowed_list,
        "allow_origin_regex": os.getenv("ALLOWED_ORIGIN_REGEX", None),
        "auth_bypass": os.getenv("AUTH_BYPASS", "false").lower() == "true",
        "firebase_project_id": os.getenv("FIREBASE_PROJECT_ID"),
    }


settings = get_settings()

app = FastAPI(
    title="Corallo TaxOps Auditor API",
    description="FastAPI wrapper that calls the existing auditor_inference pipeline.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings["allowed_origins"] or ["*"],
    allow_origin_regex=settings["allow_origin_regex"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)


@app.on_event("startup")
async def startup_event() -> None:
    init_db()
    seed_demo_data()

DEMO_USER = User(
    id="demo-user",
    email="demo.cpa@example.com",
    name="Demo CPA",
    roles=["partner", "manager"],
    firmId="firm-demo",
)

DEMO_ENGAGEMENTS = [
    EngagementSummary(
        id="eng-1",
        clientId="client-1",
        name="Demo 2024 Books Audit",
        period="FY2024",
        status="Fieldwork",
        progress=65,
        risk="Medium",
        summary={
            "dataReadiness": 70,
            "modulesRun": 2,
            "findingsOpen": 3,
            "highSeverity": 1,
        },
        createdAt=datetime(2024, 1, 1),
        updatedAt=datetime(2024, 6, 1),
    ),
]

DEMO_CLIENTS = [
    Client(
        id="client-1",
        name="Demo Manufacturing Co.",
        code="DEMO-MFG",
        status="active",
        industry="Manufacturing",
        risk="Medium",
        yearEnd="12/31",
        createdAt=datetime(2024, 1, 1),
        updatedAt=datetime(2024, 6, 1),
        engagements=DEMO_ENGAGEMENTS,
    ),
]


def verify_firebase_token(auth_header: Optional[str] = Header(None, alias="Authorization")) -> Dict[str, Any]:
    """Validate the Firebase-issued JWT. Can be bypassed for local dev via AUTH_BYPASS=true."""
    if settings["auth_bypass"]:
        return {"uid": "dev-user", "email": "dev@example.com"}
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")
    token = auth_header.split(" ", 1)[1]
    # Try internal JWT first, fallback to Firebase verification for legacy clients.
    try:
        payload = decode_token(token)
        if payload:
            return payload
    except Exception:
        pass
    try:
        request = google_requests.Request()
        decoded = id_token.verify_firebase_token(token, request, audience=settings["firebase_project_id"])
    except Exception as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid or expired token.") from exc
    if not decoded:
        raise HTTPException(status_code=401, detail="Invalid token.")
    return decoded


def _require_client_in_firm(db: Session, client_id: str, firm_id: str) -> ClientORM:
    client = db.query(ClientORM).filter(ClientORM.id == client_id, ClientORM.firm_id == firm_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


def _require_engagement_in_firm(db: Session, engagement_id: str, firm_id: str) -> EngagementORM:
    engagement = (
        db.query(EngagementORM)
        .join(ClientORM, ClientORM.id == EngagementORM.client_id)
        .filter(EngagementORM.id == engagement_id, ClientORM.firm_id == firm_id)
        .first()
    )
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return engagement


def _infer_source(content_type: Optional[str]) -> str:
    if not content_type:
        return "upload_binary"
    lowered = content_type.lower()
    if "pdf" in lowered:
        return "upload_pdf"
    if "json" in lowered:
        return "upload_json"
    return "upload_binary"


def _map_citations(raw: Any) -> List[Citation]:
    citations: List[Citation] = []
    for ref in raw or []:
        if not isinstance(ref, dict):
            continue
        label = ref.get("label") or ref.get("source") or ""
        url = ref.get("url") or ""
        citations.append(Citation(label=label, url=url))
    return citations


def _normalize_finding(issue: Dict[str, Any], *, default_doc_type: str, default_tax_year: int) -> Finding:
    cond = issue.get("condition")
    cond_str = cond.get("expr") if isinstance(cond, dict) else cond
    fields = issue.get("fields") or []
    field_paths = issue.get("field_paths") or []
    return Finding(
        id=str(issue.get("id") or issue.get("code") or ""),
        code=str(issue.get("code") or issue.get("id") or ""),
        severity=str(issue.get("severity") or ""),
        rule_type=str(issue.get("rule_type") or "structural"),
        category=issue.get("category"),
        message=str(issue.get("message") or ""),
        summary=issue.get("summary"),
        doc_type=str(issue.get("doc_type") or default_doc_type),
        tax_year=int(issue.get("tax_year") or default_tax_year or 0),
        fields=list(fields) if isinstance(fields, list) else [],
        field_paths=list(field_paths) if isinstance(field_paths, list) else [],
        citations=_map_citations(issue.get("citations")),
        rule_source=issue.get("rule_source"),
        condition=str(cond_str) if cond_str is not None else None,
        extras=issue.get("extras") or {},
        tags=list(issue.get("tags") or []),
    )


def _build_summary(findings: List[Finding], total_rules: int) -> Summary:
    by_severity: Dict[str, int] = {"error": 0, "warning": 0, "info": 0}
    for f in findings:
        sev = (f.severity or "").lower()
        if sev in by_severity:
            by_severity[sev] += 1
        else:
            by_severity[sev] = by_severity.get(sev, 0) + 1
    by_rule_type: Dict[str, int] = {}
    for f in findings:
        rt = f.rule_type
        if not rt:
            continue
        key = str(rt)
        by_rule_type[key] = by_rule_type.get(key, 0) + 1
    if not by_rule_type:
        by_rule_type = {}
    return Summary(
        total_rules_evaluated=total_rules,
        total_findings=len(findings),
        by_severity=by_severity,
        by_rule_type=by_rule_type,
    )


def _infer_ruleset(findings: List[Finding]) -> Optional[str]:
    sources = {f.rule_source for f in findings if f.rule_source}
    if len(sources) == 1:
        src = sources.pop()
        return src.replace(".yaml", "")
    return None


async def _process_audit_upload(
    file: UploadFile,
    doc_type: Optional[str],
    tax_year: Optional[int],
    user: Dict[str, Any],
    *,
    request_id: str,
    received_at: datetime,
) -> Any:
    base_doc_id = Path(file.filename or "upload").stem or f"doc-{uuid.uuid4().hex}"
    base_tax_year = int(tax_year) if tax_year else 0
    base_doc_type = doc_type or ""
    metadata = AuditDocumentMetadata(
        filename=file.filename,
        content_type=file.content_type,
        pages=None,
        source=_infer_source(file.content_type),
    )

    def _error_response(status_code: int, *, message: str):
        processed_at = datetime.now(timezone.utc)
        resp = AuditResponse(
            request_id=request_id,
            doc_id=base_doc_id,
            doc_type=base_doc_type or "UNKNOWN",
            tax_year=base_tax_year,
            received_at=received_at,
            processed_at=processed_at,
            status="error",
            summary=Summary(
                total_rules_evaluated=0,
                total_findings=0,
                by_severity={"error": 0, "warning": 0, "info": 0},
                by_rule_type={},
            ),
            document_metadata=metadata,
            findings=[],
            engine=EngineInfo(ruleset=None, version=None, evaluation_time_ms=None),
        )
        logger.warning("Audit request %s failed: %s", request_id, message)
        return fastapi_response(status_code, resp.dict())

    content = await file.read()
    if not content:
        return _error_response(400, message="Empty file uploaded.")

    logger.info("Processing upload for user=%s file=%s type=%s", user.get("uid"), file.filename, file.content_type)
    try:
        doc = parse_document_bytes(file.filename or "upload", content)
    except ImportError as exc:
        return _error_response(
            400,
            message=f"Install optional OCR/PDF dependencies on the server to handle this file type: {exc}",
        )
    except ValueError as exc:
        return _error_response(400, message=str(exc))

    if doc_type:
        doc["doc_type"] = doc_type
    if tax_year:
        doc["tax_year"] = int(tax_year)

    try:
        result = audit_document(
            doc,
            chunk_index_path=settings["chunk_index_path"],
            base_model=settings["base_model"],
            adapter_dir=settings["adapter_dir"],
            merge_strategy=settings["merge_strategy"],
            device=settings["device"],
            use_4bit=settings["use_4bit"],
            max_new_tokens=settings["max_new_tokens"],
            temperature=settings["temperature"],
            top_p=settings["top_p"],
            do_sample=settings["do_sample"],
            skip_llm=settings["skip_llm"],
            llm_endpoint=settings["llm_endpoint"],
            http_timeout=settings["http_timeout"],
        )
    except ValueError as exc:
        return _error_response(400, message=str(exc))

    processed_at = datetime.now(timezone.utc)
    resolved_doc = result.get("doc", {}) if isinstance(result, dict) else {}
    resolved_doc_id = resolved_doc.get("doc_id") or base_doc_id
    resolved_doc_type = resolved_doc.get("doc_type") or resolved_doc.get("form_type") or base_doc_type or "UNKNOWN"
    resolved_tax_year = int(resolved_doc.get("tax_year") or base_tax_year or 0)
    registry_doc_type = resolved_doc_type
    if resolved_doc_type and not rule_engine.registry.get_rules(resolved_doc_type):
        alt = resolved_doc_type.replace("-", "")
        if rule_engine.registry.get_rules(alt):
            registry_doc_type = alt

    issues = result.get("rule_issues", []) if isinstance(result, dict) else []
    findings = [_normalize_finding(i, default_doc_type=resolved_doc_type, default_tax_year=resolved_tax_year) for i in issues if isinstance(i, dict)]
    total_rules = len(rule_engine.registry.get_rules(registry_doc_type)) if registry_doc_type else 0
    summary = _build_summary(findings, total_rules)
    engine_info = EngineInfo(
        ruleset=_infer_ruleset(findings),
        version=os.getenv("ENGINE_VERSION"),
        evaluation_time_ms=result.get("rule_eval_ms") if isinstance(result, dict) else None,
    )

    response = AuditResponse(
        request_id=request_id,
        doc_id=resolved_doc_id,
        doc_type=str(resolved_doc_type),
        tax_year=resolved_tax_year,
        received_at=received_at,
        processed_at=processed_at,
        status="ok",
        summary=summary,
        document_metadata=AuditDocumentMetadata(
            filename=metadata.filename or resolved_doc.get("meta", {}).get("source_file"),
            content_type=metadata.content_type,
            pages=resolved_doc.get("meta", {}).get("pages") if isinstance(resolved_doc.get("meta"), dict) else None,
            source=metadata.source or resolved_doc.get("meta", {}).get("source"),
        ),
        findings=findings,
        engine=engine_info,
    )
    return response


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def root() -> Dict[str, str]:
    return {"service": "corallo-taxops-backend", "status": "ok"}


@app.get("/api/firm/info", response_model=FirmInfo)
async def firm_info() -> FirmInfo:
    """Return demo firm metadata without requiring auth."""
    return FirmInfo(id="firm-demo", name="TaxOps Firm", logo_url=None)


@app.get("/api/firm/summary", response_model=FirmSummary)
async def firm_summary() -> FirmSummary:
    """Return simple firm-level dashboard counts."""
    return FirmSummary(
        totalClients=10,
        activeEngagements=5,
        highSeverityFindings=2,
        upcomingReports=3,
    )


@app.get("/api/clients", response_model=List[Client])
async def list_clients(ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> List[Client]:
    clients = db.query(ClientORM).filter(ClientORM.firm_id == ctx.firm.id).all()
    result: List[Client] = []
    for c in clients:
        engagements = db.query(EngagementORM).filter(EngagementORM.client_id == c.id).all()
        result.append(
            Client(
                id=c.id,
                name=c.name,
                code=c.code or "",
                status=c.status,
                industry="General",
                risk="Medium",
                yearEnd="12/31",
                createdAt=c.created_at,
                updatedAt=c.updated_at,
                engagements=[
                    EngagementSummary(
                        id=e.id,
                        clientId=c.id,
                        name=e.name,
                        period="",
                        status=e.status,
                        progress=0,
                        risk="Medium",
                        summary={},
                        createdAt=e.created_at,
                        updatedAt=e.updated_at,
                    )
                    for e in engagements
                ],
            )
        )
    return result


@app.get("/api/clients/{client_id}", response_model=Client)
async def get_client(client_id: str, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> Client:
    c = _require_client_in_firm(db, client_id, ctx.firm.id)
    engagements = db.query(EngagementORM).filter(EngagementORM.client_id == c.id).all()
    return Client(
        id=c.id,
        name=c.name,
        code=c.code or "",
        status=c.status,
        industry="General",
        risk="Medium",
        yearEnd="12/31",
        createdAt=c.created_at,
        updatedAt=c.updated_at,
        engagements=[
            EngagementSummary(
                id=e.id,
                clientId=c.id,
                name=e.name,
                period="",
                status=e.status,
                progress=0,
                risk="Medium",
                summary={},
                createdAt=e.created_at,
                updatedAt=e.updated_at,
            )
            for e in engagements
        ],
    )


@app.get("/api/clients/{client_id}/engagements", response_model=List[EngagementSummary])
async def list_client_engagements(
    client_id: str, ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)
) -> List[EngagementSummary]:
    _require_client_in_firm(db, client_id, ctx.firm.id)
    engagements = db.query(EngagementORM).filter(EngagementORM.client_id == client_id).all()
    return [
        EngagementSummary(
            id=e.id,
            clientId=client_id,
            name=e.name,
            period="",
            status=e.status,
            progress=0,
            risk="Medium",
            summary={},
            createdAt=e.created_at,
            updatedAt=e.updated_at,
        )
        for e in engagements
    ]


@app.post("/api/books/{engagement_id}/trial-balance", response_model=TrialBalanceIngestResponse)
async def ingest_trial_balance(
    engagement_id: str,
    request: Request,
    file: UploadFile | None = File(None),
    user: Dict[str, Any] = Depends(verify_firebase_token),
) -> TrialBalanceIngestResponse:
    """Ingest trial balance CSV or JSON rows."""
    _ = user
    try:
        if file:
            content = await file.read()
            if not content:
                raise ValueError("Empty file uploaded.")
            rows = parse_tb_rows_from_csv(content.decode("utf-8"))
        else:
            try:
                body = await request.json()
            except Exception:
                body = None
            if isinstance(body, dict) and "rows" in body:
                rows = parse_tb_rows_from_list(body.get("rows") or [])
            elif isinstance(body, list):
                rows = parse_tb_rows_from_list(body)
            else:
                raise ValueError("Provide a CSV file or JSON payload with rows.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    save_trial_balance(engagement_id, rows)
    return TrialBalanceIngestResponse(
        rows_ingested=len(rows),
        total_debit=sum((r.debit for r in rows), Decimal("0")),
        total_credit=sum((r.credit for r in rows), Decimal("0")),
    )


@app.post("/api/books/{engagement_id}/gl", response_model=GLIngestResponse)
async def ingest_general_ledger(
    engagement_id: str,
    request: Request,
    file: UploadFile | None = File(None),
    user: Dict[str, Any] = Depends(verify_firebase_token),
) -> GLIngestResponse:
    """Ingest general ledger CSV or JSON rows and group into transactions."""
    _ = user
    gl_entries = []
    try:
        if file:
            content = await file.read()
            if not content:
                raise ValueError("Empty file uploaded.")
            decoded = content.decode("utf-8")
            txns = parse_transactions_from_csv(decoded)
            gl_entries = parse_gl_entries_from_csv(decoded)
        else:
            try:
                body = await request.json()
            except Exception:
                body = None
            if isinstance(body, list):
                txns = parse_transactions_from_rows(body)
                gl_entries = parse_gl_entries_from_rows(body)
            elif isinstance(body, dict) and "rows" in body:
                rows = body.get("rows") or []
                txns = parse_transactions_from_rows(rows)
                gl_entries = parse_gl_entries_from_rows(rows)
            else:
                raise ValueError("Provide a CSV file or JSON payload with rows.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    save_transactions(engagement_id, txns)
    save_gl_entries(engagement_id, gl_entries)
    total_debit = sum((line.debit for txn in txns for line in txn.lines), Decimal("0"))
    total_credit = sum((line.credit for txn in txns for line in txn.lines), Decimal("0"))
    return GLIngestResponse(transactions_ingested=len(txns), total_debit=total_debit, total_credit=total_credit)


@app.get("/api/books/{engagement_id}/findings", response_model=List[BookFinding])
async def books_findings(
    engagement_id: str,
    user: Dict[str, Any] = Depends(verify_firebase_token),
    db: Session = Depends(get_db),
) -> List[BookFinding]:
    """Run basic Books of Accounts checks."""
    _ = user
    findings = run_books_rules(engagement_id)
    if findings:
        save_domain_findings(db, engagement_id, "books", findings)
    return findings


@app.get("/api/income/{engagement_id}/findings", response_model=List[DomainFinding])
async def income_findings(engagement_id: str, db: Session = Depends(get_db)) -> List[DomainFinding]:
    """Run income domain rules."""
    findings = run_income_rules(engagement_id)
    if findings:
        save_domain_findings(db, engagement_id, "income", findings)
    return findings


@app.get("/api/expenses/{engagement_id}/findings", response_model=List[DomainFinding])
async def expense_findings(engagement_id: str, db: Session = Depends(get_db)) -> List[DomainFinding]:
    """Run expense domain rules."""
    findings = run_expense_rules(engagement_id)
    if findings:
        save_domain_findings(db, engagement_id, "expense", findings)
    return findings


@app.post("/api/bank/{engagement_id}/statements")
async def upload_bank_statement(
    engagement_id: str,
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """Upload and parse a bank statement CSV for an engagement."""
    _ = user
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV bank statements are supported in this prototype.")
    content = await file.read()
    try:
        entries = parse_bank_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse bank CSV: {exc}") from exc
    save_bank_entries(engagement_id, entries)
    return {"engagement_id": engagement_id, "entries": len(entries)}


@app.get("/api/bank/{engagement_id}/findings", response_model=List[DomainFinding])
async def bank_findings(engagement_id: str, db: Session = Depends(get_db)) -> List[DomainFinding]:
    """Run bank domain rules."""
    findings = run_bank_rules(engagement_id)
    if findings:
        save_domain_findings(db, engagement_id, "bank", findings)
    return findings


@app.post("/api/docs/{engagement_id}/upload", response_model=DocumentMetadata)
async def upload_document(
    engagement_id: str,
    file: UploadFile = File(...),
    metadata: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    Upload a single document with JSON metadata.
    metadata is a JSON string containing:
      - type (str)
      - amount (optional float)
      - date (optional YYYY-MM-DD)
      - counterparty (optional)
      - external_ref (optional)
    """
    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid metadata JSON: {exc}") from exc

    doc_type = (meta.get("type") or "").strip()
    if not doc_type:
        raise HTTPException(status_code=400, detail="Document type is required.")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file.")

    parsed_date = None
    if meta.get("date"):
        try:
            parsed_date = datetime.strptime(meta["date"], "%Y-%m-%d").date()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {exc}") from exc

    amount = meta.get("amount")
    counterparty = meta.get("counterparty") or None
    external_ref = meta.get("external_ref") or None

    obj = DocumentORM(
        engagement_id=str(engagement_id),
        filename=file.filename,
        content=raw,
        type=doc_type,
        amount=float(amount) if amount is not None else None,
        date=parsed_date,
        counterparty=counterparty,
        external_ref=external_ref,
        uploaded_by="demo",
    )
    db.add(obj)
    db.flush()

    match = match_document_to_bank_entries(engagement_id, obj)
    if match:
        domain, entry_id = match
        link = DocumentLinkORM(
            engagement_id=str(engagement_id),
            domain=domain,
            entry_id=entry_id,
            doc_id=obj.id,
        )
        db.add(link)

    db.commit()
    db.refresh(obj)

    return DocumentMetadata.from_orm(obj)


@app.get("/api/docs/{engagement_id}", response_model=DocumentListResponse)
async def list_documents(engagement_id: str, db: Session = Depends(get_db)):
    docs = (
        db.query(DocumentORM)
        .filter(DocumentORM.engagement_id == str(engagement_id))
        .order_by(DocumentORM.uploaded_at.desc())
        .all()
    )
    return DocumentListResponse(documents=[DocumentMetadata.from_orm(d) for d in docs])


@app.get("/api/docs/{engagement_id}/findings", response_model=List[DomainFinding])
async def get_document_findings(
    engagement_id: str,
    db: Session = Depends(get_db),
):
    findings = run_document_rules(db, engagement_id)
    if findings:
        save_domain_findings(db, engagement_id, "documents", findings)
    return findings


@app.get("/api/controls/{engagement_id}/findings", response_model=List[DomainFinding])
async def get_controls_findings(
    engagement_id: str,
    db: Session = Depends(get_db),
) -> List[DomainFinding]:
    findings = run_controls_rules(engagement_id)
    if findings:
        save_domain_findings(db, engagement_id, "controls", findings)
    return findings


@app.post("/api/payroll/{engagement_id}/employees")
async def upload_payroll_employees(
    engagement_id: str,
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """Upload payroll employee master CSV."""
    _ = user
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV employee master is supported in this prototype.")
    content = await file.read()
    try:
        employees = parse_payroll_employee_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse payroll employees CSV: {exc}") from exc
    save_payroll_employees(engagement_id, employees)
    return {"engagement_id": engagement_id, "employees": len(employees)}


@app.post("/api/payroll/{engagement_id}/entries")
async def upload_payroll_entries(
    engagement_id: str,
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """Upload payroll entries CSV."""
    _ = user
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV payroll exports are supported in this prototype.")
    content = await file.read()
    try:
        entries = parse_payroll_entries_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse payroll entries CSV: {exc}") from exc
    save_payroll_entries(engagement_id, entries)
    return {"engagement_id": engagement_id, "entries": len(entries)}


@app.get("/api/payroll/{engagement_id}/findings", response_model=List[DomainFinding])
async def payroll_findings(engagement_id: str, db: Session = Depends(get_db)) -> List[DomainFinding]:
    """Run payroll domain rules."""
    findings = run_payroll_rules(engagement_id)
    if findings:
        save_domain_findings(db, engagement_id, "payroll", findings)
    return findings


@app.post("/api/inventory/{engagement_id}/items")
async def upload_inventory_items(
    engagement_id: str,
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """Upload inventory item master CSV."""
    _ = user
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV item master is supported in this prototype.")
    content = await file.read()
    try:
        items = parse_inventory_items_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse inventory items CSV: {exc}") from exc
    save_inventory_items(engagement_id, items)
    return {"engagement_id": engagement_id, "items": len(items)}


@app.post("/api/inventory/{engagement_id}/movements")
async def upload_inventory_movements(
    engagement_id: str,
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """Upload inventory movements CSV."""
    _ = user
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV inventory movements are supported in this prototype.")
    content = await file.read()
    try:
        moves = parse_inventory_movements_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse inventory movements CSV: {exc}") from exc
    save_inventory_movements(engagement_id, moves)
    return {"engagement_id": engagement_id, "movements": len(moves)}


@app.get("/api/inventory/{engagement_id}/findings", response_model=List[DomainFinding])
async def inventory_findings(engagement_id: str, db: Session = Depends(get_db)) -> List[DomainFinding]:
    """Run inventory domain rules."""
    findings = run_inventory_rules(engagement_id)
    if findings:
        save_domain_findings(db, engagement_id, "inventory", findings)
    return findings


@app.post("/api/liabilities/{engagement_id}/loans")
async def upload_loans(
    engagement_id: str,
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """Upload loan master CSV."""
    _ = user
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV loans file is supported in this prototype.")
    content = await file.read()
    try:
        loans = parse_loans_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse loans CSV: {exc}") from exc
    save_loans(engagement_id, loans)
    return {"engagement_id": engagement_id, "loans": len(loans)}


@app.post("/api/liabilities/{engagement_id}/loan-periods")
async def upload_loan_periods(
    engagement_id: str,
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """Upload loan period schedule CSV."""
    _ = user
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV loan periods file is supported in this prototype.")
    content = await file.read()
    try:
        periods = parse_loan_periods_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse loan periods CSV: {exc}") from exc
    save_loan_periods(engagement_id, periods)
    return {"engagement_id": engagement_id, "periods": len(periods)}


@app.post("/api/liabilities/{engagement_id}/ap")
async def upload_ap_entries(
    engagement_id: str,
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """Upload AP ledger CSV."""
    _ = user
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV AP ledger file is supported in this prototype.")
    content = await file.read()
    try:
        entries = parse_ap_entries_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse AP CSV: {exc}") from exc
    save_ap_entries(engagement_id, entries)
    return {"engagement_id": engagement_id, "entries": len(entries)}


@app.get("/api/liabilities/{engagement_id}/findings", response_model=List[DomainFinding])
async def liabilities_findings(engagement_id: str, db: Session = Depends(get_db)) -> List[DomainFinding]:
    """Run liabilities domain rules."""
    findings = run_liabilities_rules(engagement_id)
    if findings:
        save_domain_findings(db, engagement_id, "liabilities", findings)
    return findings


@app.post("/api/assets/{engagement_id}/register")
async def upload_assets_register(
    engagement_id: str,
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """Upload fixed asset register CSV."""
    _ = user
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV asset register is supported in this prototype.")
    content = await file.read()
    try:
        assets = parse_assets_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse asset register CSV: {exc}") from exc
    save_assets(engagement_id, assets)
    return {"engagement_id": engagement_id, "assets": len(assets)}


@app.post("/api/assets/{engagement_id}/depreciation")
async def upload_assets_depreciation(
    engagement_id: str,
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """Upload asset depreciation schedule CSV."""
    _ = user
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV depreciation file is supported in this prototype.")
    content = await file.read()
    try:
        entries = parse_depreciation_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse depreciation CSV: {exc}") from exc
    save_depreciation_entries(engagement_id, entries)
    return {"engagement_id": engagement_id, "entries": len(entries)}


@app.get("/api/assets/{engagement_id}/findings", response_model=List[DomainFinding])
async def assets_findings(engagement_id: str, db: Session = Depends(get_db)) -> List[DomainFinding]:
    """Run assets domain rules."""
    findings = run_assets_rules(engagement_id)
    if findings:
        save_domain_findings(db, engagement_id, "assets", findings)
    return findings


@app.get("/api/engagements/{engagement_id}/stats", response_model=EngagementStatsResponse)
async def engagement_stats(
    engagement_id: str,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_current_context),
) -> EngagementStatsResponse:
    _require_engagement_in_firm(db, engagement_id, ctx.firm.id)
    return compute_engagement_stats(db, engagement_id)


@app.get("/api/engagements/{engagement_id}/findings", response_model=List[DomainFinding])
async def engagement_findings(
    engagement_id: str,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_current_context),
) -> List[DomainFinding]:
    """Return all persisted findings for an engagement across domains."""
    _require_engagement_in_firm(db, engagement_id, ctx.firm.id)
    rows = (
        db.query(FindingORM)
        .filter(FindingORM.engagement_id == engagement_id)
        .order_by(FindingORM.created_at.desc())
        .all()
    )
    return [
        DomainFinding(
            id=r.id,
            engagement_id=r.engagement_id,
            domain=r.domain,
            severity=r.severity,
            code=r.code,
            message=r.message,
            metadata=r.metadata_json or {},
        )
        for r in rows
    ]


@app.post("/api/compliance/{engagement_id}/returns")
async def upload_compliance_returns(
    engagement_id: str,
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """Upload tax returns summary CSV."""
    _ = user
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV returns file is supported in this prototype.")
    content = await file.read()
    try:
        rows = parse_returns_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse returns CSV: {exc}") from exc
    save_tax_returns(engagement_id, rows)
    return {"engagement_id": engagement_id, "rows": len(rows)}


@app.post("/api/compliance/{engagement_id}/books")
async def upload_compliance_books(
    engagement_id: str,
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """Upload books turnover CSV for tax types."""
    _ = user
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV books tax export is supported in this prototype.")
    content = await file.read()
    try:
        rows = parse_books_tax_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse books tax CSV: {exc}") from exc
    save_books_tax(engagement_id, rows)
    return {"engagement_id": engagement_id, "rows": len(rows)}


@app.get("/api/compliance/{engagement_id}/findings", response_model=List[DomainFinding])
async def compliance_findings(engagement_id: str, db: Session = Depends(get_db)) -> List[DomainFinding]:
    """Run compliance reconciliation rules."""
    findings = run_compliance_rules(engagement_id)
    if findings:
        save_domain_findings(db, engagement_id, "compliance", findings)
    return findings


@app.get("/api/engagements/{engagement_id}/findings", response_model=List[DomainFinding])
async def engagement_findings(engagement_id: str, db: Session = Depends(get_db)) -> List[DomainFinding]:
    """Return all persisted findings for an engagement across domains."""
    rows = (
        db.query(FindingORM)
        .filter(FindingORM.engagement_id == engagement_id)
        .order_by(FindingORM.created_at.desc())
        .all()
    )
    return [
        DomainFinding(
            id=r.id,
            engagement_id=r.engagement_id,
            domain=r.domain,
            severity=r.severity,
            code=r.code,
            message=r.message,
            metadata=r.metadata_json or {},
        )
        for r in rows
    ]


@app.post("/audit-document", response_model=AuditResponse)
async def audit_document_endpoint(
    file: UploadFile = File(...),
    doc_type: Optional[str] = Form(None),
    tax_year: Optional[int] = Form(None),
    user: Dict[str, Any] = Depends(verify_firebase_token),
) -> Any:
    """Accept a PDF/image/JSON upload, run the auditor pipeline, and return findings."""
    received_at = datetime.now(timezone.utc)
    request_id = uuid.uuid4().hex
    result = await _process_audit_upload(
        file,
        doc_type,
        tax_year,
        user,
        request_id=request_id,
        received_at=received_at,
    )
    return result


@app.post("/audit-report", response_class=HTMLResponse)
async def audit_report_endpoint(
    file: UploadFile = File(...),
    doc_type: Optional[str] = Form(None),
    tax_year: Optional[int] = Form(None),
    user: Dict[str, Any] = Depends(verify_firebase_token),
) -> Any:
    """Accept a document, run audit, and return an HTML report."""
    received_at = datetime.now(timezone.utc)
    request_id = uuid.uuid4().hex
    audit_result = await _process_audit_upload(
        file,
        doc_type,
        tax_year,
        user,
        request_id=request_id,
        received_at=received_at,
    )
    # Error responses are JSONResponse objects; pass through directly.
    if not isinstance(audit_result, AuditResponse):
        return audit_result
    html = render_audit_report(audit_result)
    return HTMLResponse(content=html, media_type="text/html")


@app.exception_handler(HTTPException)
async def http_error_handler(_, exc: HTTPException):  # type: ignore[override]
    return fastapi_response(exc.status_code, {"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_error_handler(_, exc: Exception):  # type: ignore[override]
    logger.exception("Unhandled error: %s", exc)
    return fastapi_response(500, {"detail": "Internal server error"})


def fastapi_response(status_code: int, payload: Dict[str, Any]):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status_code, content=payload)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
