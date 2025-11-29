"""FastAPI wrapper around the Corallo TaxOps auditor inference pipeline.

This service exposes a single `/audit-document` endpoint that accepts PDF/Image/JSON uploads,
verifies Firebase-issued JWTs, routes the file through lightweight parsing, and returns
deterministic + LLM findings from the existing auditor_inference package.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

# Ensure the repo root (auditor_inference, auditor, etc.) is importable when deployed.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from auditor_inference.document_extraction import parse_document_bytes  # noqa: E402
from auditor_inference.inference import audit_document  # noqa: E402

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


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def root() -> Dict[str, str]:
    return {"service": "corallo-taxops-backend", "status": "ok"}


@app.post("/audit-document")
async def audit_document_endpoint(
    file: UploadFile = File(...),
    doc_type: Optional[str] = Form(None),
    tax_year: Optional[int] = Form(None),
    user: Dict[str, Any] = Depends(verify_firebase_token),
) -> Dict[str, Any]:
    """Accept a PDF/image/JSON upload, run the auditor pipeline, and return findings."""
    start = time.time()
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")

    logger.info("Processing upload for user=%s file=%s type=%s", user.get("uid"), file.filename, file.content_type)
    try:
        doc = parse_document_bytes(file.filename or "upload", content)
    except ImportError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Install optional OCR/PDF dependencies on the server to handle this file type: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        # Gracefully surface validation issues (e.g., unsupported tax year) as 400 to the client.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    elapsed_ms = int((time.time() - start) * 1000)
    payload = {
        "processing_time_ms": elapsed_ms,
        "doc_id": result.get("doc", {}).get("doc_id"),
        "rule_issues": result.get("rule_issues", []),
        "rule_findings": result.get("rule_findings", []),
        "llm_findings": result.get("llm_findings", []),
        "merged_findings": result.get("merged_findings", []),
        "audit_trail": {
            "retrieval_sources": result.get("audit_trail", {}).get("retrieval_sources", []),
            "timestamp": result.get("audit_trail", {}).get("timestamp"),
            "llm_mode": result.get("audit_trail", {}).get("llm_mode"),
            "llm_skipped": result.get("audit_trail", {}).get("llm_skipped"),
            "rule_issues": result.get("audit_trail", {}).get("rule_issues", []),
        },
        "metadata": result.get("audit_trail", {}),
    }
    return payload


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
