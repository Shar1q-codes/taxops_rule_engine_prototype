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
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

# Ensure the repo root (auditor_inference, auditor, etc.) is importable when deployed.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from engine import rule_engine  # noqa: E402
from auditor_inference.document_extraction import parse_document_bytes  # noqa: E402
from auditor_inference.inference import audit_document  # noqa: E402
from backend.reporting import render_audit_report  # noqa: E402
from backend.schemas import (  # noqa: E402
    AuditResponse,
    Citation,
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
)
from backend.accounting_store import get_transactions, get_trial_balance, save_transactions, save_trial_balance  # noqa: E402
from backend.books_ingestion import (  # noqa: E402
    parse_tb_rows_from_csv,
    parse_tb_rows_from_list,
    parse_transactions_from_csv,
    parse_transactions_from_rows,
)
from backend.books_rules import BookFinding, run_books_rules  # noqa: E402
from backend.books_schemas import GLIngestResponse, TrialBalanceIngestResponse  # noqa: E402
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
    try:
        request = google_requests.Request()
        decoded = id_token.verify_firebase_token(token, request, audience=settings["firebase_project_id"])
    except Exception as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid or expired token.") from exc
    if not decoded:
        raise HTTPException(status_code=401, detail="Invalid token.")
    return decoded


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
    metadata = DocumentMetadata(
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
        document_metadata=DocumentMetadata(
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
async def firm_info(user: Dict[str, Any] = Depends(verify_firebase_token)) -> FirmInfo:
    """Return firm metadata for the authenticated user."""
    firm_id = user.get("firm_id") or user.get("firmId") or "firm-demo"
    firm_name = user.get("firm_name") or user.get("firmName") or "TaxOps Firm"
    logo_url = user.get("firm_logo_url") or user.get("firmLogoUrl")
    return FirmInfo(id=str(firm_id), name=str(firm_name), logo_url=logo_url)


@app.get("/api/firm/summary", response_model=FirmSummary)
async def firm_summary(user: Dict[str, Any] = Depends(verify_firebase_token)) -> FirmSummary:
    """Return simple firm-level dashboard counts. Replace with real data source when available."""
    _ = user  # token validation already performed
    return FirmSummary(
        totalClients=10,
        activeEngagements=5,
        highSeverityFindings=2,
        upcomingReports=3,
    )


@app.get("/auth/me", response_model=MeResponse)
async def get_current_user() -> MeResponse:
    """Stub auth endpoint that always returns a demo user."""
    return MeResponse(user=DEMO_USER)


@app.get("/api/clients", response_model=List[Client])
async def list_clients() -> List[Client]:
    return DEMO_CLIENTS


@app.get("/api/clients/{client_id}", response_model=Client)
async def get_client(client_id: str) -> Client:
    for client in DEMO_CLIENTS:
        if client.id == client_id:
            return client
    raise HTTPException(status_code=404, detail="Client not found")


@app.get("/api/clients/{client_id}/engagements", response_model=List[EngagementSummary])
async def list_client_engagements(client_id: str) -> List[EngagementSummary]:
    for client in DEMO_CLIENTS:
        if client.id == client_id:
            return client.engagements or []
    raise HTTPException(status_code=404, detail="Client not found")


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
    try:
        if file:
            content = await file.read()
            if not content:
                raise ValueError("Empty file uploaded.")
            txns = parse_transactions_from_csv(content.decode("utf-8"))
        else:
            try:
                body = await request.json()
            except Exception:
                body = None
            if isinstance(body, list):
                txns = parse_transactions_from_rows(body)
            elif isinstance(body, dict) and "rows" in body:
                txns = parse_transactions_from_rows(body.get("rows") or [])
            else:
                raise ValueError("Provide a CSV file or JSON payload with rows.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    save_transactions(engagement_id, txns)
    total_debit = sum((line.debit for txn in txns for line in txn.lines), Decimal("0"))
    total_credit = sum((line.credit for txn in txns for line in txn.lines), Decimal("0"))
    return GLIngestResponse(transactions_ingested=len(txns), total_debit=total_debit, total_credit=total_credit)


@app.get("/api/books/{engagement_id}/findings", response_model=List[BookFinding])
async def books_findings(
    engagement_id: str,
    user: Dict[str, Any] = Depends(verify_firebase_token),
) -> List[BookFinding]:
    """Run basic Books of Accounts checks."""
    _ = user
    findings = run_books_rules(engagement_id)
    return findings


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
