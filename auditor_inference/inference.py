"""Unified inference pipeline for Corallo TaxOps Auditor.

This module orchestrates:
- Document loading (JSON or raw text provided by caller)
- Lightweight retrieval over a chunk index (jsonl)
- Prompt construction with grounding context and uncertainty handling
- LoRA model loading and generation
- Parsing + normalization of LLM findings and merging with deterministic rule findings

Heavy dependencies (torch/transformers/peft) are imported lazily to keep test environments light.
"""

from __future__ import annotations

import json
import math
import uuid
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

from auditor.findings import filter_llm_findings_by_doc, merge_findings, normalize_llm_findings
from engine import RuleEngine, rule_engine as default_rule_engine
from training_prep.formatter import format_auditor_prompt

logger = logging.getLogger(__name__)

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover - optional dependency for remote LLM
    requests = None


# ---------- Retrieval utilities (lightweight, CPU-friendly) ----------
def _tokenize(text: str) -> List[str]:
    """Very small tokenizer: lowercase split on whitespace."""
    return text.lower().split()


def _bow_embed(text: str) -> Counter:
    """Simple bag-of-words embedding using term counts."""
    return Counter(_tokenize(text))


def _cosine(a: Counter, b: Counter) -> float:
    """Cosine similarity between two sparse vectors."""
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b.get(k, 0) for k in a)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def load_chunk_index(path: str | Path) -> List[Dict[str, Any]]:
    """
    Load a JSONL chunk index into memory.
    Each line should be a JSON object with at minimum:
      - "id": str
      - "text": str
    Optionally:
      - "title": str
      - "section": str
      - any other metadata fields.
    """
    p = Path(path)
    if not p.exists():
        return []
    chunks: List[Dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and "text" in obj:
                    chunks.append(obj)
            except json.JSONDecodeError:
                continue
    return chunks


def call_remote_llm(
    endpoint: str,
    doc: Dict[str, Any],
    retrieval_sources: List[Dict[str, Any]],
    timeout: int = 60,
) -> Dict[str, Any]:
    """
    Call a remote LLM HTTP endpoint for findings.

    Expected request JSON:
    {
      "doc": {...},
      "retrieval_sources": [...]
    }

    Expected response JSON:
    {
      "llm_findings": [...],
      "raw_model_output": "..."   # optional
    }
    """
    if requests is None:
        raise RuntimeError("requests library is required for remote LLM calls.")
    payload = {"doc": doc, "retrieval_sources": retrieval_sources}
    resp = requests.post(endpoint, json=payload, timeout=timeout)
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError as exc:  # JSON decode error
        logger.error("Remote LLM endpoint returned non-JSON response: %s", resp.text[:500])
        raise RuntimeError("Remote LLM endpoint returned invalid JSON") from exc
    return data


def retrieve_relevant_chunks(doc: Dict[str, Any], chunk_index: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Lightweight retrieval over the local chunk index.
    - Builds a simple query string from doc fields.
    - Uses bag-of-words cosine similarity for scoring.
    - Returns top_k chunks with id, score, title/section if present, and a short snippet.
    """
    if not chunk_index:
        return []

    parts = [
        str(doc.get("doc_type", "")),
        str(doc.get("tax_year", "")),
        json.dumps(doc.get("amounts", {}), ensure_ascii=False),
        json.dumps(doc.get("employer", {}), ensure_ascii=False),
        json.dumps(doc.get("taxpayer", {}), ensure_ascii=False),
    ]
    query_text = " ".join(parts)
    query_vec = _bow_embed(query_text)

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for ch in chunk_index:
        text = str(ch.get("text", ""))
        score = _cosine(query_vec, _bow_embed(text))
        scored.append((score, ch))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_items = scored[: top_k if top_k > 0 else 5]

    results: List[Dict[str, Any]] = []
    for score, ch in top_items:
        snippet = ch.get("text", "")[:200]
        results.append(
            {
                "id": ch.get("id") or ch.get("chunk_id") or ch.get("source") or "",
                "score": float(score),
                "title": ch.get("title") or ch.get("source") or "",
                "section": ch.get("section", ""),
                "snippet": snippet,
                "url": ch.get("url", ""),
            }
        )

    # If all scores are zero/empty, still return the first up to top_k entries
    if not results and chunk_index:
        fallback = chunk_index[: top_k if top_k > 0 else 5]
        results = [
            {
                "id": ch.get("id") or ch.get("chunk_id") or ch.get("source") or "",
                "score": 0.0,
                "title": ch.get("title") or ch.get("source") or "",
                "section": ch.get("section", ""),
                "snippet": ch.get("text", "")[:200],
                "url": ch.get("url", ""),
            }
            for ch in fallback
        ]

    return results


def build_retrieval_context(chunks: Iterable[Dict[str, Any]]) -> str:
    """Format retrieved chunks for prompt grounding."""
    parts = []
    for idx, ch in enumerate(chunks, start=1):
        src = ch.get("source") or ch.get("id") or f"chunk-{idx}"
        url = ch.get("url", "")
        text = ch.get("text", "")
        parts.append(f"[{idx}] Source: {src} {f'({url})' if url else ''}\n{text}")
    return "\n\n".join(parts)


# ---------- Prompt + parsing ----------
def build_prompt(doc: Dict[str, Any], retrieval_context: str | None = None) -> str:
    """Create the instruction-response style prompt with grounding context."""
    base = format_auditor_prompt(doc)
    guidance = (
        "\n\nYou must ground every finding in the DOCUMENT and any retrieved sources below.\n"
        "If data is missing or insufficient, return an 'Uncertain' finding with appropriate tags and no invented facts.\n"
        "Include citation_hint using the retrieved source labels where applicable.\n"
    )
    context_block = ""
    if retrieval_context:
        context_block = f"\n\nRETRIEVED SOURCES:\n{retrieval_context}\n"
    return f"### Instruction:\n{base}{guidance}{context_block}\n### Response:\n"


def extract_json_array(text: str) -> Any:
    """Extract first JSON array from model output."""
    start = text.find("[")
    if start == -1:
        raise ValueError("No '[' found in completion output; cannot locate JSON array.")
    for i in range(start + 1, len(text) + 1):
        if text[i - 1] == "]":
            candidate = text[start:i]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    raise ValueError("Failed to parse any JSON array from completion output.")


# ---------- Model helpers (lazy heavy imports) ----------
def select_device(device_arg: str):
    import torch  # imported lazily

    device_arg = device_arg.lower()
    if device_arg == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device_arg == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA requested but not available.")
        return torch.device("cuda")
    if device_arg == "cpu":
        return torch.device("cpu")
    raise ValueError(f"Unknown device argument: {device_arg!r}")


def load_model_and_tokenizer(base_model: str, adapter_dir: str | Path, device, use_4bit: bool = False):
    """Load base model + LoRA adapter (lazy heavy imports)."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel, prepare_model_for_kbit_training

    adapter_dir = str(adapter_dir)
    tokenizer = AutoTokenizer.from_pretrained(adapter_dir, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model_kwargs: Dict[str, Any] = {}
    if use_4bit:
        model_kwargs.update(
            {
                "load_in_4bit": True,
                "bnb_4bit_quant_type": "nf4",
                "bnb_4bit_use_double_quant": True,
                "bnb_4bit_compute_dtype": torch.float16,
            }
        )

    base = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.float16 if device.type == "cuda" else torch.float32,
        device_map="auto" if device.type == "cuda" else None,
        **model_kwargs,
    )
    if use_4bit:
        base = prepare_model_for_kbit_training(base)

    model = PeftModel.from_pretrained(base, adapter_dir)
    model.to(device)
    model.eval()
    return model, tokenizer


def generate_completion(
    model,
    tokenizer,
    prompt: str,
    device,
    max_new_tokens: int = 512,
    temperature: float = 0.1,
    top_p: float = 0.9,
    do_sample: bool = False,
) -> str:
    """Run generation for the given prompt and return decoded text."""
    import torch

    encoded = tokenizer(prompt, return_tensors="pt", truncation=True)
    encoded = {k: v.to(device) for k, v in encoded.items()}
    gen_kwargs: Dict[str, Any] = {"max_new_tokens": max_new_tokens, "pad_token_id": tokenizer.eos_token_id}
    if do_sample:
        gen_kwargs.update({"do_sample": True, "temperature": float(temperature), "top_p": float(top_p)})
    else:
        gen_kwargs["do_sample"] = False
    with torch.no_grad():
        output_ids = model.generate(**encoded, **gen_kwargs)
    return tokenizer.decode(output_ids[0], skip_special_tokens=True)


# ---------- Rule engine integration ----------
def load_rules_for_doc(doc_type: str) -> List[Dict[str, Any]]:
    """Load YAML rules for the given doc_type."""
    rules_dir = Path(__file__).resolve().parent.parent / "rules"
    filename = "w2.yaml" if doc_type == "W2" else "1099_int.yaml" if doc_type == "1099-INT" else None
    if not filename:
        return []
    rules_path = rules_dir / filename
    if not rules_path.exists():
        return []
    with rules_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or []


# ---------- End-to-end audit ----------
def audit_document(
    doc: Dict[str, Any],
    *,
    chunk_index_path: str | Path,
    base_model: str,
    adapter_dir: str | Path,
    merge_strategy: str = "no_duplicates",
    device: str = "cpu",
    use_4bit: bool = False,
    max_new_tokens: int = 512,
    temperature: float = 0.1,
    top_p: float = 0.9,
    do_sample: bool = False,
    skip_llm: bool = False,
    llm_endpoint: Optional[str] = None,
    http_timeout: int = 60,
) -> Dict[str, Any]:
    """Run retrieval-augmented audit and merge deterministic + LLM findings."""
    doc_id = doc.get("doc_id") or f"doc-{uuid.uuid4().hex}"
    doc_type = doc.get("doc_type")
    tax_year = doc.get("tax_year")

    # Deterministic findings from the production rule engine
    rule_engine: RuleEngine = default_rule_engine
    rule_issues: List[Dict[str, Any]] = []
    try:
        rule_issues = rule_engine.evaluate(doc, form_type=doc_type, tax_year=tax_year)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Rule engine evaluation failed: %s", exc)
        if isinstance(exc, ValueError):
            raise

    def _issue_to_finding(issue: Dict[str, Any]) -> Dict[str, Any]:
        citations = issue.get("citations") or []
        citation_hint_parts = []
        for ref in citations:
            if not isinstance(ref, dict):
                continue
            src = ref.get("source") or ""
            url = ref.get("url") or ""
            citation_hint_parts.append(f"{src} {url}".strip())
        citation_hint = "; ".join([p for p in citation_hint_parts if p])
        return {
            "finding_id": uuid.uuid4().hex,
            "doc_id": doc_id,
            "source": "RULE_ENGINE_V2",
            "code": issue.get("id"),
            "category": issue.get("name"),
            "severity": issue.get("severity"),
            "summary": issue.get("message"),
            "details": issue.get("message"),
            "suggested_action": issue.get("hint") or "Review and correct the highlighted fields.",
            "citation_hint": citation_hint,
            "tags": issue.get("fields") or [],
            "fields": issue.get("fields") or [],
            "citations": citations,
            "rule_source": issue.get("rule_source"),
            "condition": issue.get("condition"),
        }

    rule_findings = [_issue_to_finding(i) for i in rule_issues]

    # Retrieval context
    chunks = load_chunk_index(chunk_index_path)
    retrievals = retrieve_relevant_chunks(doc, chunks, top_k=5)
    retrieval_context = build_retrieval_context(
        [{"text": r.get("snippet", ""), "source": r.get("title") or r.get("id", ""), "url": r.get("url", "")} for r in retrievals]
    )

    prompt = ""
    raw_output = ""
    normalized_llm: List[Dict[str, Any]] = []
    llm_raw: Dict[str, Any] | None = None

    if skip_llm:
        llm_raw = {"skipped": True, "reason": "LLM inference skipped via --skip-llm"}
    elif llm_endpoint:
        remote = call_remote_llm(llm_endpoint, doc, retrievals, timeout=http_timeout)
        llm_raw_output = remote.get("raw_model_output", "")
        llm_list = remote.get("llm_findings", [])
        if not isinstance(llm_list, list):
            llm_list = []
        normalized_llm = normalize_llm_findings(doc_id, llm_list) if llm_list else []
        llm_raw = {"raw_output": llm_raw_output, "mode": "REMOTE"}
    else:
        # Prompt + model inference
        prompt = build_prompt(doc, retrieval_context)
        torch_device = select_device(device)
        model, tokenizer = load_model_and_tokenizer(base_model, adapter_dir, torch_device, use_4bit=use_4bit)
        raw_output = generate_completion(
            model=model,
            tokenizer=tokenizer,
            prompt=prompt,
            device=torch_device,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
            do_sample=do_sample,
        )

        # Strip prompt prefix if the model echoed it
        completion = raw_output[len(prompt) :].strip() if raw_output.startswith(prompt) else raw_output.strip()

        # Parse LLM findings safely
        try:
            llm_findings_raw = extract_json_array(completion)
        except Exception:
            llm_findings_raw = []

        normalized_llm = normalize_llm_findings(doc_id, llm_findings_raw) if llm_findings_raw else []
        llm_raw = {"prompt": prompt, "raw_output": raw_output, "mode": "LOCAL"}
    filtered_llm = filter_llm_findings_by_doc(doc, normalized_llm)
    merged = merge_findings(rule_findings, filtered_llm, strategy=merge_strategy)

    audit_trail = {
        "doc_id": doc_id,
        "doc_type": doc_type,
        "tax_year": tax_year,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_preview": prompt[:2000],
        "raw_model_output": raw_output[:4000] if raw_output else "",
        "llm_skipped": skip_llm,
        "llm_mode": "REMOTE" if (llm_endpoint and not skip_llm) else ("LOCAL" if (not skip_llm and not llm_endpoint) else "SKIPPED"),
        "retrieval_sources": retrievals,
        "rule_findings": rule_findings,
        "rule_issues": rule_issues,
        "llm_findings": filtered_llm,
        "merged_findings": merged,
    }
    return {
        "doc": doc,
        "rule_findings": rule_findings,
        "rule_issues": rule_issues,
        "llm_findings": filtered_llm,
        "merged_findings": merged,
        "audit_trail": audit_trail,
        "llm_raw": llm_raw,
    }


# ---------- CLI entry point ----------
def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Unified inference pipeline for Corallo TaxOps Auditor.")
    parser.add_argument("--doc-file", required=True, help="JSON document file path.")
    parser.add_argument("--chunk-index", required=False, default="sample_data/chunk_index.jsonl", help="Path to chunk_index.jsonl.")
    parser.add_argument("--base-model", required=True, help="Base HF model name/path (e.g., mistralai/Mistral-7B-v0.1).")
    parser.add_argument("--adapter-dir", required=True, help="LoRA adapter directory (e.g., outputs/auditor_mistral_lora).")
    parser.add_argument("--device", default="cpu", help="Device: cpu | cuda | auto.")
    parser.add_argument("--use-4bit", action="store_true", help="Enable 4-bit loading if bitsandbytes installed.")
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--do-sample", action="store_true")
    parser.add_argument(
        "--llm-endpoint",
        type=str,
        default=None,
        help="Optional HTTP endpoint for remote LLM inference (JSON in/out). If set and skip-llm is False, audit_document will call this instead of loading a local HF model.",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip loading the HF model and only run deterministic rule findings (no LLM inference).",
    )
    args = parser.parse_args()

    doc_path = Path(args.doc_file)
    with doc_path.open("r", encoding="utf-8") as handle:
        doc = json.load(handle)

    result = audit_document(
        doc,
        chunk_index_path=args.chunk_index,
        base_model=args.base_model,
        adapter_dir=args.adapter_dir,
        merge_strategy="no_duplicates",
        device=args.device,
        use_4bit=args.use_4bit,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        do_sample=args.do_sample,
        skip_llm=args.skip_llm,
        llm_endpoint=args.llm_endpoint,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    _cli()
