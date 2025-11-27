# Corallo TaxOps – AI-Powered CPA Audit Prototype

Production-ready prototype that lets CPAs authenticate, securely upload W-2/PDF/Image/JSON files, run the Corallo Auditor pipeline via FastAPI, and review categorized findings in a Next.js dashboard.

## Repo Layout
- `backend/` – FastAPI wrapper (`/audit-document`) around `auditor_inference`.
- `frontend/` – Next.js 14 (App Router, Tailwind + ShadCN-style UI, Firebase Auth).
- `auditor_inference/`, `auditor/`, `rules/`, `sample_data/` – Existing inference, rules, and sample assets.
- `render.yaml` – Render deployment definition for the API.
- `netlify.toml` – Netlify deploy config for the frontend.

## Prerequisites
- Python 3.10+
- Node 18+
- Firebase project (Email/Password + Google providers enabled)
- Render (or Fly.io) account for backend; Netlify for frontend (free tiers)

## Backend – FastAPI (Render/Fly/Local)
**Install & run locally**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export PYTHONPATH=..                                # ensure auditor_inference imports resolve
cp .env.example .env                                 # fill values
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

**Key settings (`backend/.env.example`)**
- `FIREBASE_PROJECT_ID` – required for JWT verification.
- `ALLOWED_ORIGINS` – comma list of allowed frontends (e.g., `http://localhost:3000,https://your-site.netlify.app`).
- `CHUNK_INDEX_PATH` – defaults to `sample_data/chunk_index.jsonl`.
- `AUDITOR_BASE_MODEL` / `AUDITOR_ADAPTER_DIR` – only needed if you enable local LLM; defaults assume repo paths.
- `LLM_ENDPOINT` – optional remote LLM endpoint; set `AUDITOR_SKIP_LLM=false` to enable.
- `AUTH_BYPASS` – `true` only for local dev.

**API**
- `POST /audit-document` (multipart/form-data)
  - Headers: `Authorization: Bearer <firebase_id_token>`
  - Body: `file` (PDF/JSON/PNG/JPG/TIFF/BMP), optional `doc_type`
  - Response: `{ processing_time_ms, doc_id, rule_findings, llm_findings, merged_findings, audit_trail }`
- `GET /health`

**Example request (with Firebase token)**
```bash
TOKEN="eyJhbGciOiJSUzI1NiIsImtpZCI6..."   # firebase ID token
curl -X POST http://localhost:8000/audit-document \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@sample_data/w2_zero_withholding.json"
```

**Render deployment**
- Repo root includes `render.yaml` (web service, free plan).
- Build command: `pip install -r backend/requirements.txt`
- Start command: `PYTHONPATH=. cd backend && uvicorn app:app --host 0.0.0.0 --port $PORT`
- Set env vars in Render dashboard: `FIREBASE_PROJECT_ID`, `ALLOWED_ORIGINS` (Netlify URL), `AUDITOR_SKIP_LLM=true`, optional `LLM_ENDPOINT`, `AUTH_BYPASS=false`.

## Frontend – Next.js 14 + Tailwind + Firebase (Netlify)
**Install & run locally**
```bash
cd frontend
npm install
cp .env.example .env.local   # fill Firebase + backend URL
npm run dev
```
Visit `http://localhost:3000` → sign in (email/password or Google) → upload → view results.

**Netlify deploy**
- `netlify.toml` sets base to `frontend`, build `npm run build`, publish `.next`.
- Configure environment variables in Netlify UI:
  - `NEXT_PUBLIC_API_URL=https://<render-backend>.onrender.com`
  - Firebase keys: `NEXT_PUBLIC_FIREBASE_API_KEY`, `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`, `NEXT_PUBLIC_FIREBASE_PROJECT_ID`, `NEXT_PUBLIC_FIREBASE_APP_ID`
- Connect GitHub repo, enable automatic deploys.

**UI Flow**
1) Login (email/password or Google via Firebase Auth)  
2) Upload/drag-drop PDF/Image/JSON (+ optional doc type)  
3) Loader/progress indicator while calling backend with JWT  
4) Results rendered as cards (rule, LLM, merged findings) + retrieval trace  
5) Error badges/toasts for failed uploads

## Auth Flow
- Client obtains Firebase ID token after sign-in.
- Requests to `/audit-document` carry `Authorization: Bearer <token>`.
- Backend validates token against `FIREBASE_PROJECT_ID` via Google certs.
- `AUTH_BYPASS` can be enabled locally only; keep `false` in production.

## Example Response (truncated)
```json
{
  "processing_time_ms": 420,
  "doc_id": "doc-123",
  "rule_findings": [
    {"code": "W2_ZERO_WITHHOLDING", "severity": "HIGH", "description": "Withholding is zero", "confidence": 0.98}
  ],
  "llm_findings": [],
  "merged_findings": [
    {"code": "W2_ZERO_WITHHOLDING", "severity": "HIGH", "description": "Withholding is zero", "confidence": 0.98}
  ],
  "audit_trail": {
    "llm_mode": "REMOTE",
    "llm_skipped": false,
    "retrieval_sources": [{"id": "irs-2024-1", "title": "IRS Withholding Guidance"}]
  }
}
```

## Security Notes (pre-production checklist)
- Enable HTTPS on Render + Netlify; set strict `ALLOWED_ORIGINS`.
- Keep `AUTH_BYPASS=false` outside local dev.
- Store secrets in platform env vars (never commit `.env`).
- Optional: configure short Firebase session lifetimes and enforce email domain allowlist.
- Disable request/response body logging; current API only logs metadata.
- Files are processed in memory; avoid mounting persistent volumes.
- If enabling local LLM, review GPU/4-bit settings and ensure no PII is logged.

## Local Dev Commands
- Backend: `PYTHONPATH=.. uvicorn app:app --reload --port 8000`
- Frontend: `npm run dev` (Netlify build mirrors `npm run build`)
- Tests (existing rule/LLM tests): `python -m pytest`

## Notes on Inference
- By default `AUDITOR_SKIP_LLM=true` to keep the prototype lightweight; set `LLM_ENDPOINT` + `AUDITOR_SKIP_LLM=false` to call a hosted LLM.
- Retrieval uses `sample_data/chunk_index.jsonl`; swap in your IRS chunk index via `CHUNK_INDEX_PATH`.
