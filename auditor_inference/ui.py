"""Streamlit UI for Corallo TaxOps Auditor inference.

Run with:
  pip install streamlit
  streamlit run auditor_inference/ui.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

# Allow running as a module (python -m auditor_inference.ui)
# or as a script (python auditor_inference/ui.py)
try:
    from .document_extraction import parse_document
    from .inference import audit_document, load_chunk_index
except ImportError:  # pragma: no cover - runtime fallback for script execution
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from auditor_inference.document_extraction import parse_document  # type: ignore
    from auditor_inference.inference import audit_document, load_chunk_index  # type: ignore


def launch_app() -> None:
    """Launch Streamlit UI for uploading docs and running audit."""
    import streamlit as st  # imported lazily

    @st.cache_resource
    def get_chunk_index(path: str) -> List[Dict[str, Any]]:
        """Load and cache the chunk index from JSONL."""
        return load_chunk_index(path)

    st.set_page_config(page_title="Corallo TaxOps Auditor", layout="wide")
    st.title("Corallo TaxOps – Document Audit (Local Rule Engine + Skip LLM)")
    st.write(
        "Upload a JSON tax document or PDF to run the deterministic audit engine. "
        "LLM inference is intentionally skipped on this machine."
    )

    uploaded = st.file_uploader(
        "Upload W-2 / tax document (JSON or PDF)",
        type=["json", "pdf"],
    )

    if not uploaded:
        return

    # Persist the uploaded file to a temporary path so parse_document can read it
    suffix = uploaded.name.split(".")[-1] if "." in uploaded.name else "bin"
    tmp_path = Path(f"tmp_upload.{suffix}")
    tmp_path.write_bytes(uploaded.getbuffer())

    try:
        # 1. Parse into normalized internal doc
        doc = parse_document(tmp_path)

        st.subheader("Parsed document")
        st.json(doc)

        if st.button("Run audit"):
            # 2. Load chunk index once (cached)
            chunk_index = get_chunk_index("sample_data/chunk_index.jsonl")

            # 3. Run full audit in skip-LLM mode
            result = audit_document(
                doc=doc,
                chunk_index_path="sample_data/chunk_index.jsonl",
                base_model="mistralai/Mistral-7B-v0.1",
                adapter_dir="outputs/auditor_mistral_lora",
                device="cpu",
                max_new_tokens=256,
                use_4bit=False,
                # Ensure no HF model is loaded locally
                skip_llm=True,
            )

            # 4. Render sections
            st.subheader("Rule engine findings")
            st.json(result.get("rule_findings", []))

            st.subheader("LLM findings (skip-LLM mode)")
            st.json(result.get("llm_findings", []))

            st.subheader("Merged findings")
            st.json(result.get("merged_findings", []))

            st.subheader("Audit trail")
            st.json(result.get("audit_trail", {}))

    finally:
        if tmp_path.exists():
            tmp_path.unlink()


if __name__ == "__main__":
    launch_app()
