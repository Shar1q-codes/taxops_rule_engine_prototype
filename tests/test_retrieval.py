import json
from pathlib import Path

from auditor_inference.inference import audit_document, load_chunk_index, retrieve_relevant_chunks


def test_load_chunk_index(tmp_path):
    chunk_file = tmp_path / "chunks.jsonl"
    lines = [
        {"id": "c1", "text": "IRS Pub 15 withholding guidance"},
        {"id": "c2", "text": "IRS Pub 505 backup withholding"},
    ]
    with chunk_file.open("w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line) + "\n")

    loaded = load_chunk_index(chunk_file)
    assert len(loaded) == 2
    assert loaded[0]["id"] == "c1"


def test_retrieve_relevant_chunks_non_empty():
    chunk_index = [
        {"id": "c1", "text": "W-2 wages and withholding guidance from IRS."},
        {"id": "c2", "text": "1099-INT interest income rules."},
    ]
    doc = {"doc_type": "W2", "tax_year": 2024, "amounts": {"wages": 1000}}
    retrieved = retrieve_relevant_chunks(doc, chunk_index, top_k=2)
    assert retrieved
    assert any(r["id"] == "c1" for r in retrieved)


def test_audit_document_populates_retrieval_sources(tmp_path):
    chunk_file = tmp_path / "chunks.jsonl"
    lines = [
        {"id": "c1", "text": "W-2 wages and Social Security wage base guidance."},
        {"id": "c2", "text": "Medicare tax rate information."},
    ]
    with chunk_file.open("w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line) + "\n")

    doc = {
        "doc_id": "d1",
        "doc_type": "W2",
        "tax_year": 2024,
        "amounts": {"wages": 1000},
        "employer": {"ein": "12-3456789"},
        "taxpayer": {"ssn": "123-45-6789"},
    }

    result = audit_document(
        doc,
        chunk_index_path=str(chunk_file),
        base_model="dummy",
        adapter_dir="dummy",
        skip_llm=True,
    )
    retrievals = result.get("audit_trail", {}).get("retrieval_sources", [])
    assert retrievals
    assert any(r["id"] == "c1" for r in retrievals)
